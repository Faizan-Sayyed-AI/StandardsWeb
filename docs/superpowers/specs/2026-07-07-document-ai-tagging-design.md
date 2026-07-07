# Document AI Tagging & Tag-Powered Search

## Context

Managers/admins upload a document (PDF/DOCX/XLSX) as a version of a standard via
`POST /api/v1/standards/{standard_id}/documents` (`document_service.upload_document`,
`documents.py`). Today the only searchable text about a standard is
`iso_reference` / `title` / `tc_committee` (`standard_service.list_standards` /
`get_grouped_standards`).

The user has a working external AI service reachable over HTTP (currently an ngrok
tunnel) that accepts a file upload and returns structured tags:

```json
{
  "document_type": "standard",
  "summary": "ASME B1.13M-2005, Metric Screw Threads: M Profile",
  "department": "Mechanical Engineering",
  "category_01_metadata": ["American National Standard", "Metric Screw Threads", "M Profile"],
  "category_02_primary_subject": ["Screw Threads", "Thread Profiles", "Design and Tolerances"],
  "category_03_technical_methods": ["ISO System of Limits and Fits", "Tolerance Grade", "..."],
  "category_04_nlp_ai_models": [],
  "category_05_application_domain": ["Mechanical Engineering", "Manufacturing", "Quality Control"],
  "category_06_system_architecture": [],
  "category_07_statistical_mathematical": ["Cosine Similarity", "Thread Profile Analysis"],
  "category_08_semantic_conceptual": [],
  "category_09_long_tail_phrases": []
}
```

This spec wires document uploads to that service and makes the result searchable.
Scope is backend + frontend; no changes to the external service itself.

## Decisions (user-confirmed)

- **Trigger**: every document upload (not the separate "mark as purchased" action).
- **Processing**: async — a Celery background task, not inline in the upload request.
  Upload succeeds/returns exactly as it does today regardless of tagging outcome.
- **Endpoint config**: admin-configurable via a DB-stored setting (same pattern as
  SMTP config), not an env var — ngrok URLs rotate and this must be changeable
  without a redeploy.
- **Auth**: the service takes no auth today. The settings schema still reserves an
  optional API key field so one can be added later without a migration.
- **Failure handling**: retry with exponential backoff (same shape as
  `poll_feed`/`send_email_notification`); after retries are exhausted, write an
  audit log entry (`document.tagging_failed`) so it's visible rather than silently
  dropped.
- **Data model**: a new `document_tags` table (one row per document version), not
  new columns on `documents` — keeps file-storage concerns and AI-derived metadata
  separate.
- **Search surface**: both — (1) the existing Standards search box also matches
  tag/summary/department text, and (2) the Documents tab on a standard's detail
  page displays the tags/summary/department once available.
- **Manual retry**: a "Retry tagging" action (manager/admin) that resets a
  document's tag row and re-dispatches the task — needed because a permanently
  failed tag (e.g. the URL was misconfigured at upload time) would otherwise
  require re-uploading the file to fix.

## Data model

New enum + table, migration `0011_add_document_tags.py`:

```python
class DocumentTagStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    failed = "failed"

class DocumentTag(AsyncBase):
    __tablename__ = "document_tags"

    id: Mapped[uuid.UUID]              # PK, gen_random_uuid()
    document_id: Mapped[uuid.UUID]     # FK documents.id, UNIQUE, ondelete=CASCADE, indexed
    status: Mapped[DocumentTagStatus]  # server_default "pending"
    document_type: Mapped[str | None]      # String(100)
    summary: Mapped[str | None]            # Text
    department: Mapped[str | None]         # String(255)
    raw_response: Mapped[dict | None]      # JSONB — the full response as-is
    search_text: Mapped[str | None]        # Text — see below
    error_message: Mapped[str | None]      # Text
    requested_at: Mapped[datetime]         # server_default now()
    completed_at: Mapped[datetime | None]
```

`search_text` is `summary + " " + department + " " + <every string in every
category_XX array>`, lowercased, space-joined — a deliberately simple flattening so
it can be matched with a plain `ILIKE '%term%'`, consistent with how
`Standard.title`/`iso_reference` search already works. No full-text-search engine
is introduced.

`UNIQUE` on `document_id` — one tag row per document version, upserted in place by
retries/re-runs.

## Service layer

New `backend/app/services/document_tag_service.py` owns all `DocumentTag` reads/
writes, used by the three call sites below (upload, the Celery task, and the
retry endpoint) so none of them touch the table directly:

```python
async def create_pending_tag(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag: ...
async def get_tag_for_document(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag | None: ...
async def mark_tag_result(document_id: uuid.UUID, db: AsyncSession, *, status: DocumentTagStatus,
                           document_type: str | None = None, summary: str | None = None,
                           department: str | None = None, raw_response: dict | None = None,
                           search_text: str | None = None, error_message: str | None = None) -> None: ...
async def reset_tag_to_pending(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag: ...
```

## Upload flow changes

`document_service.upload_document()`: immediately after inserting the `Document`
row (same transaction), call `document_tag_service.create_pending_tag(doc.id, db)`.
This means the UI shows "Tagging pending…" from the moment the upload response
comes back, instead of a window with no tag row at all. After the transaction
commits, dispatch `tag_document.delay(str(doc.id))` — same place the existing
`send_email_notification.delay(...)` call already happens for the
`document_uploaded` event.

## Admin-configurable endpoint

New module `backend/app/core/document_tagging_config.py`, mirroring
`smtp_config.py` exactly: `get_active_document_tagging_settings(db)` /
`set_active_document_tagging_settings(db, data)`, backed by a new `system_config`
row under key `"document_tagging_config"`:

```json
{"DOCUMENT_TAGGING_URL": "...", "DOCUMENT_TAGGING_API_KEY": "..."}
```

Reuses the existing `MASKED_PASSWORD_PLACEHOLDER` constant/convention from
`smtp_config.py` for the API key field, including the same "blank or masked value
on PATCH means leave unchanged" fix already applied to SMTP config — no repeat of
that bug here.

New endpoints in `admin.py`:
- `GET /api/v1/admin/document-tagging-config` — admin only, key masked
- `PATCH /api/v1/admin/document-tagging-config` — admin only

New schemas in `schemas/admin.py`: `DocumentTaggingConfigResponse`,
`DocumentTaggingConfigUpdate` (`DOCUMENT_TAGGING_URL: str` required,
`DOCUMENT_TAGGING_API_KEY: str` optional).

If `DOCUMENT_TAGGING_URL` is unset, the task treats this as a non-retryable skip
(see below) rather than an error — uploads work today even before an admin
configures tagging.

## Celery task

New `backend/app/tasks/documents.py`, new `documents` queue (added alongside
`feeds`/`notifications`/`maintenance` in `celery_app.py`'s `task_routes`, and to
the `worker` service's `-Q` list in `docker-compose.yml` — otherwise the task is
never consumed).

```python
@celery.task(name="app.tasks.documents.tag_document", queue="documents", bind=True, max_retries=3)
def tag_document(self, document_id: str) -> dict:
    ...
```

`_tag_document_async(document_id)`:
1. Load the `Document` row. If missing, log and return (nothing to do).
2. Load tagging config. If `DOCUMENT_TAGGING_URL` is blank, call
   `document_tag_service.mark_tag_result(status=failed, error_message="Document
   tagging is not configured")` and return `{"status": "skipped"}` — no Celery
   retry (retrying won't fix a missing config; an admin can hit "Retry tagging"
   once they've configured it).
3. Get the file's bytes via the existing storage abstraction: `download_url()`
   returns either a local filesystem path (open directly — the `worker` container
   already mounts the same `./backend/storage` volume as `web`) or a presigned S3
   URL (fetch via `httpx.get`).
4. `POST` the bytes as multipart `file=` to `DOCUMENT_TAGGING_URL` via `httpx`
   (reuses the `httpx` dependency already used in `tasks/feeds.py`).
5. Parse the JSON response, build `search_text`, call
   `document_tag_service.mark_tag_result(status=ok, document_type=..., summary=...,
   department=..., raw_response=..., search_text=...)`.
6. On any exception in steps 3–5: re-raise, letting the Celery task's `except`
   block retry with `60 * 2**retries` backoff (same shape as `poll_feed`). After
   `max_retries` (3) is exhausted: call `document_tag_service.mark_tag_result(
   status=failed, error_message=...)`, and write an audit log entry
   (`action="document.tagging_failed"`, `resource_type="document"`,
   `resource_id=document_id`, `payload={"error": ...}`).

## Retry endpoint

`POST /api/v1/documents/{document_id}/retag` (manager/admin, `ManagerOrAdminUser`),
in `documents.py`:
1. Verify the document exists (404 if not).
2. Call `document_tag_service.reset_tag_to_pending(document_id, db)`.
3. Dispatch `tag_document.delay(str(document_id))`.
4. Return the updated tag row.

Available regardless of current status (not just `failed`) — e.g. useful if the
tagging service's output quality improves and someone wants a fresher tag.

## API schema additions

`schemas/document.py`:

```python
class DocumentTagResponse(BaseModel):
    status: str  # "pending" | "ok" | "failed"
    document_type: str | None
    summary: str | None
    department: str | None
    raw_response: dict | None
    error_message: str | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
```

`DocumentResponse` gains `tags: DocumentTagResponse | None = None` (populated via a
join in `document_service.list_documents`/`upload_document`). `raw_response` is
included so the frontend can render the 9 `category_XX` arrays as badges without a
second endpoint.

## Search integration

`standard_service.list_standards()` / `get_grouped_standards()`: the existing
`search` condition (currently `OR`s `iso_reference`/`title`/`tc_committee` ILIKE)
gains one more branch:

```python
Standard.id.in_(
    select(Document.standard_id)
    .join(DocumentTag, DocumentTag.document_id == Document.id)
    .where(DocumentTag.search_text.ilike(search_term))
)
```

Same `search_term` (`f"%{search.strip()}%"`) already built for the other
conditions — no new query parameter, this is a transparent broadening of the
existing search box.

## Frontend changes

**New admin page**, `DocumentTaggingConfigPage.tsx` — same shape/layout as
`SMTPConfigPage.tsx` (including the "don't preload the masked key into an editable
field" fix already applied there): a URL field and an optional API key field,
`GET`/`PATCH` against the new admin endpoint. Added to the admin nav alongside the
existing SMTP Settings entry.

**`frontend/src/api/documents.ts`**: `Document` interface gains
`tags: DocumentTag | null`; add `retagDocument(documentId): Promise<Document>`
calling the new retry endpoint.

**`StandardDetailPage.tsx` Documents tab**: under each document row, render:
- `status === "pending"`: a subtle "Tagging pending…" label
- `status === "ok"`: the `summary` as a line of text, `department` as a small
  badge, and every non-empty `category_XX` array flattened into small tag pills
  (reusing the existing `Badge` component)
- `status === "failed"`: an "Tagging failed" indicator (red, matching the
  existing status-badge color conventions elsewhere in this app) with a "Retry
  tagging" button (manager/admin only) calling `retagDocument`

**`StandardsPage.tsx`**: no UI change — the search box already sends `search` to
the backend, which now matches more broadly. Optionally (not required for this
spec) the search input's placeholder text could mention documents, but that's
cosmetic and left to a follow-up.

## Error handling & edge cases

- Upload always succeeds regardless of tagging service availability — tagging is
  fully decoupled via the pending-row-then-async-task pattern.
- Deleting a document (`soft_delete_document`) leaves its `DocumentTag` row
  intact (soft-delete doesn't touch tags; `ON DELETE CASCADE` only matters if a
  `Document` row is ever hard-deleted, which this app doesn't do today).
- If the AI service is unreachable, `document.tagging_failed` audit entries make
  the failure visible in the existing Audit Logs page (no new UI surface needed).
- If the AI service returns malformed/unexpected JSON, that's treated as a normal
  exception in step 5 above and goes through the same retry/failure path.

## Out of scope (explicitly deferred)

- A standalone documents browse/search page across all standards — search stays
  folded into the existing Standards search box for now.
- Full-text search infrastructure (Postgres `tsvector`, trigram indexes) — plain
  `ILIKE` matches the rest of this codebase's existing search approach.
- Authentication on the outbound request to the tagging service (schema is
  ready, wiring is not, since the current service needs none).
- Retroactively tagging documents uploaded before this feature ships — could be
  a manual one-off script later if needed, not part of this spec.
