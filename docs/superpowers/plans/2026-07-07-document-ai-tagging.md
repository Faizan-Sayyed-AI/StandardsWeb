# Document AI Tagging & Tag-Powered Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every document uploaded to a standard gets automatically sent to an external AI tagging service in the background; the returned summary/department/category tags are stored and made searchable from the existing Standards search box, with a manual retry action if tagging fails.

**Architecture:** A new `document_tags` table (one row per document version) is written eagerly as `pending` at upload time, then filled in by a new async Celery task (`tag_document`, new `documents` queue) that POSTs the file to an admin-configurable URL and parses the JSON response. Search matches against a flattened `search_text` column via the same `ILIKE` pattern already used elsewhere in this codebase.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Celery, httpx, Postgres (JSONB), React + TanStack Query, no new dependencies.

## Global Constraints

- **No pytest suite exists in this repo** (confirmed: no `tests/` directory, no `conftest.py`). This project's established verification practice — used for every fix across this codebase's history — is live verification against the running Docker stack: `docker compose exec` + `curl` + `psql`. Every task below verifies this way, not with `pytest`. Do not introduce a pytest framework as a side effect of this plan.
- **Enums**: every Postgres enum in this codebase is created via `op.execute("CREATE TYPE x_enum AS ENUM (...)")` in the migration, then referenced in the table definition as `postgresql.ENUM(..., name="x_enum", create_type=False)`. Follow this exactly (see `0001_initial_schema.py`).
- **No ORM `relationship()` anywhere in this codebase.** Every model uses plain FK columns (`ForeignKey(...)`) and explicit `select()`/`join()` queries. Do not add `relationship()`.
- **New Celery tasks must be registered in three places or they silently never run**: (1) `task_routes` in `backend/app/celery_app.py`, (2) the `-Q` list in the `worker` service's `command:` in `docker-compose.yml`, (3) the task module itself (auto-discovered by `celery.autodiscover_tasks(["app.tasks"])`, so just creating the file under `app/tasks/` is enough for #3). This exact mistake was already made and fixed once this session for feed scheduling — don't repeat it.
- **Masked-secret settings**: `DOCUMENT_TAGGING_API_KEY` must reuse the `MASKED_PASSWORD_PLACEHOLDER` convention from `backend/app/core/smtp_config.py` — a PATCH with a blank or masked value must leave the stored secret unchanged. This exact bug was already found and fixed for SMTP config this session; don't reintroduce it here.
- **Migration numbering**: current head is `0010_add_missing_fk_indexes.py`. The new migration is `0011`.
- **Docker compose command changes**: editing `docker-compose.yml`'s `command:` for a service requires `docker compose up -d <service>` to take effect — `docker compose restart <service>` does NOT re-read the compose file and will silently keep running the old command.
- **Retry/backoff shape**: match `poll_feed` in `backend/app/tasks/feeds.py` exactly — `bind=True, max_retries=3`, `countdown = 60 * (2 ** retries)`, final failure handled distinctly from mid-retry failure.

---

### Task 1: `document_tags` migration and model

**Files:**
- Create: `backend/alembic/versions/0011_add_document_tags.py`
- Create: `backend/app/models/document_tag.py`
- Modify: `backend/app/models/__init__.py`

**Interfaces:**
- Produces: `DocumentTagStatus` enum (`pending`, `ok`, `failed`) and `DocumentTag` ORM model with columns `id, document_id, status, document_type, summary, department, raw_response, search_text, error_message, requested_at, completed_at` — used by every later task.

- [ ] **Step 1: Write the migration**

```python
"""Add document_tags table for AI-generated document tags.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE document_tag_status_enum AS ENUM ('pending', 'ok', 'failed')")

    op.create_table(
        "document_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM("pending", "ok", "failed", name="document_tag_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_document_tags_document_id", table_name="document_tags")
    op.drop_table("document_tags")
    op.execute("DROP TYPE IF EXISTS document_tag_status_enum")
```

- [ ] **Step 2: Write the model**

```python
"""
ORM model: document_tags table.

One row per document version, created eagerly at upload time (status=pending)
and filled in asynchronously by the app.tasks.documents.tag_document Celery
task. See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class DocumentTagStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    failed = "failed"


class DocumentTag(AsyncBase):
    __tablename__ = "document_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[DocumentTagStatus] = mapped_column(
        Enum(DocumentTagStatus, name="document_tag_status_enum", create_type=False),
        nullable=False,
        server_default=DocumentTagStatus.pending.value,
    )
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DocumentTag id={self.id} document_id={self.document_id} status={self.status}>"
```

- [ ] **Step 3: Register the model in `backend/app/models/__init__.py`**

Add the import and `__all__` entry, keeping the existing alphabetical order:

```python
from app.models.document import Document
from app.models.document_tag import DocumentTag
```

and in `__all__`:

```python
    "Document",
    "DocumentTag",
```

- [ ] **Step 4: Verify — apply the migration against the live stack**

```bash
docker compose up -d db redis web worker beat mailhog
docker compose exec -T web alembic upgrade head
docker compose exec -T web alembic current
```
Expected: last line prints `0011 (head)`.

```bash
docker compose exec -T db psql -U ists -d ists -c "\d document_tags"
```
Expected: shows all 11 columns with `document_id` as a unique-indexed FK, `status` as `document_tag_status_enum` defaulting to `'pending'`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0011_add_document_tags.py backend/app/models/document_tag.py backend/app/models/__init__.py
git commit -m "feat: add document_tags table for AI-generated document tags"
```

---

### Task 2: `document_tag_service.py` — CRUD helpers

**Files:**
- Create: `backend/app/services/document_tag_service.py`

**Interfaces:**
- Consumes: `DocumentTag`, `DocumentTagStatus` from `app.models.document_tag` (Task 1).
- Produces: `create_pending_tag(document_id, db) -> DocumentTag`, `get_tag_for_document(document_id, db) -> DocumentTag | None`, `get_tags_for_documents(document_ids, db) -> dict[uuid.UUID, DocumentTag]`, `mark_tag_result(document_id, db, *, status, document_type=None, summary=None, department=None, raw_response=None, search_text=None, error_message=None) -> None`, `reset_tag_to_pending(document_id, db) -> DocumentTag` — used by Task 4 (task), Task 5 (upload), Task 6 (retry endpoint + read paths).

- [ ] **Step 1: Write the service module**

```python
"""
document_tags read/write service.

Owns all access to the document_tags table — the Celery tagging task, the
upload flow, and the manual retry endpoint all go through these functions
rather than touching the table directly.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.document_tag import DocumentTag, DocumentTagStatus

log = structlog.get_logger(__name__)


async def create_pending_tag(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag:
    """Create the initial pending tag row for a freshly-uploaded document."""
    tag = DocumentTag(document_id=document_id, status=DocumentTagStatus.pending)
    db.add(tag)
    await db.flush()
    return tag


async def get_tag_for_document(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag | None:
    """Return the tag row for one document, or None if it has none (pre-feature upload)."""
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.document_id == document_id)
    )
    return result.scalar_one_or_none()


async def get_tags_for_documents(
    document_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, DocumentTag]:
    """Bulk-fetch tag rows for a list of documents, keyed by document_id (avoids N+1 queries)."""
    if not document_ids:
        return {}
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.document_id.in_(document_ids))
    )
    return {tag.document_id: tag for tag in result.scalars().all()}


async def mark_tag_result(
    document_id: uuid.UUID,
    db: AsyncSession,
    *,
    status: DocumentTagStatus,
    document_type: str | None = None,
    summary: str | None = None,
    department: str | None = None,
    raw_response: dict[str, Any] | None = None,
    search_text: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update a tag row with the outcome of a tagging attempt (success or failure)."""
    tag = await get_tag_for_document(document_id, db)
    if tag is None:
        log.error("document_tag_missing_on_result", document_id=str(document_id))
        return

    tag.status = status
    tag.document_type = document_type
    tag.summary = summary
    tag.department = department
    tag.raw_response = raw_response
    tag.search_text = search_text
    tag.error_message = error_message
    tag.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def reset_tag_to_pending(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag:
    """Reset a tag row to pending ahead of a manual re-tag. Raises NotFoundError if missing."""
    tag = await get_tag_for_document(document_id, db)
    if tag is None:
        raise NotFoundError("DocumentTag")

    tag.status = DocumentTagStatus.pending
    tag.error_message = None
    tag.completed_at = None
    await db.flush()
    return tag
```

- [ ] **Step 2: Verify — exercise every function directly against the live DB**

Pick a real document ID first:

```bash
docker compose exec -T db psql -U ists -d ists -c "SELECT id FROM documents LIMIT 1;"
```

Then, substituting that UUID for `<DOC_ID>`:

```bash
docker compose exec -T web python -c "
import asyncio, uuid
from app.database import async_session_factory
from app.services import document_tag_service as svc
from app.models.document_tag import DocumentTagStatus

DOC_ID = uuid.UUID('<DOC_ID>')

async def main():
    async with async_session_factory() as db:
        tag = await svc.create_pending_tag(DOC_ID, db)
        await db.commit()
        print('created:', tag.status)

    async with async_session_factory() as db:
        fetched = await svc.get_tag_for_document(DOC_ID, db)
        print('fetched status:', fetched.status)

        bulk = await svc.get_tags_for_documents([DOC_ID], db)
        print('bulk fetch has key:', DOC_ID in bulk)

        await svc.mark_tag_result(
            DOC_ID, db, status=DocumentTagStatus.ok,
            summary='test summary', department='Testing',
            raw_response={'a': 1}, search_text='test summary testing',
        )
        await db.commit()

    async with async_session_factory() as db:
        after_mark = await svc.get_tag_for_document(DOC_ID, db)
        print('after mark_tag_result:', after_mark.status, after_mark.summary)

        reset = await svc.reset_tag_to_pending(DOC_ID, db)
        await db.commit()
        print('after reset:', reset.status, reset.error_message)

asyncio.run(main())
"
```

Expected output:
```
created: DocumentTagStatus.pending
fetched status: DocumentTagStatus.pending
bulk fetch has key: True
after mark_tag_result: DocumentTagStatus.ok test summary
after reset: DocumentTagStatus.pending None
```

Clean up the test row so it doesn't linger:

```bash
docker compose exec -T db psql -U ists -d ists -c "DELETE FROM document_tags WHERE document_id='<DOC_ID>';"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/document_tag_service.py
git commit -m "feat: add document_tag_service CRUD helpers"
```

---

### Task 3: Admin-configurable tagging endpoint settings

**Files:**
- Create: `backend/app/core/document_tagging_config.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/api/v1/admin.py`

**Interfaces:**
- Consumes: `MASKED_PASSWORD_PLACEHOLDER` from `app.core.smtp_config` (existing).
- Produces: `get_active_document_tagging_settings(db) -> dict`, `set_active_document_tagging_settings(db, data) -> None` — used by Task 4 (Celery task) and the new admin endpoints below. `DocumentTaggingConfigResponse`, `DocumentTaggingConfigUpdate` schemas — used by the frontend admin page (Task 9).

- [ ] **Step 1: Write the config module**

Mirrors `backend/app/core/smtp_config.py` exactly, including its masked-secret fix:

```python
"""
Helper functions for fetching and updating the document AI tagging service
configuration from the database (system_config table).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.smtp_config import MASKED_PASSWORD_PLACEHOLDER
from app.models.system_config import SystemConfig

_CONFIG_KEY = "document_tagging_config"


async def get_active_document_tagging_settings(db: AsyncSession) -> dict:
    """Retrieve the document tagging service config, defaulting to blank/unconfigured."""
    stmt = select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    defaults = {
        "DOCUMENT_TAGGING_URL": "",
        "DOCUMENT_TAGGING_API_KEY": "",
    }

    if config_row:
        row_val = config_row.value
        for k in defaults:
            if k in row_val:
                defaults[k] = row_val[k]

    return defaults


async def set_active_document_tagging_settings(db: AsyncSession, data: dict) -> None:
    """
    Save the document tagging config.

    DOCUMENT_TAGGING_API_KEY is left unchanged when the incoming value is
    blank or the masked placeholder — same round-trip-safety fix already
    applied to SMTP_PASSWORD in smtp_config.py.
    """
    stmt = select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    existing_key = config_row.value.get("DOCUMENT_TAGGING_API_KEY", "") if config_row else ""
    incoming_key = data.get("DOCUMENT_TAGGING_API_KEY", "")
    api_key = (
        existing_key
        if incoming_key in ("", MASKED_PASSWORD_PLACEHOLDER)
        else incoming_key
    )

    payload = {
        "DOCUMENT_TAGGING_URL": data.get("DOCUMENT_TAGGING_URL", ""),
        "DOCUMENT_TAGGING_API_KEY": api_key,
    }

    if config_row:
        config_row.value = payload
    else:
        config_row = SystemConfig(key=_CONFIG_KEY, value=payload)
        db.add(config_row)

    await db.flush()
```

- [ ] **Step 2: Add schemas to `backend/app/schemas/admin.py`**

Add after the existing `SMTPConfigUpdate` class (after line 47 in the current file):

```python
class DocumentTaggingConfigResponse(BaseModel):
    DOCUMENT_TAGGING_URL: str
    DOCUMENT_TAGGING_API_KEY: str

    @classmethod
    def from_dict_masked(cls, data: dict) -> "DocumentTaggingConfigResponse":
        key = data.get("DOCUMENT_TAGGING_API_KEY", "")
        masked_key = MASKED_PASSWORD_PLACEHOLDER if key else ""
        return cls(
            DOCUMENT_TAGGING_URL=data.get("DOCUMENT_TAGGING_URL", ""),
            DOCUMENT_TAGGING_API_KEY=masked_key,
        )


class DocumentTaggingConfigUpdate(BaseModel):
    DOCUMENT_TAGGING_URL: str = Field(..., min_length=1)
    DOCUMENT_TAGGING_API_KEY: str = Field(default="")
```

(`MASKED_PASSWORD_PLACEHOLDER` is already imported at the top of this file.)

- [ ] **Step 3: Add endpoints to `backend/app/api/v1/admin.py`**

Add to the existing import block from `app.core.smtp_config` — change:

```python
from app.core.smtp_config import (
    MASKED_PASSWORD_PLACEHOLDER,
    get_active_smtp_settings,
    set_active_smtp_settings,
)
```

to also import the new module (new line right after):

```python
from app.core.smtp_config import (
    MASKED_PASSWORD_PLACEHOLDER,
    get_active_smtp_settings,
    set_active_smtp_settings,
)
from app.core.document_tagging_config import (
    get_active_document_tagging_settings,
    set_active_document_tagging_settings,
)
```

Add to the `from app.schemas.admin import (...)` block:

```python
from app.schemas.admin import (
    NotificationTriggerMappingCreate,
    NotificationTriggerMappingResponse,
    SMTPConfigResponse,
    SMTPConfigUpdate,
    DocumentTaggingConfigResponse,
    DocumentTaggingConfigUpdate,
    AuditLogResponse,
    WorkerStatusResponse,
    QueueDepths,
)
```

Insert these two endpoints right after `update_smtp_config` (after line 95, before the `/trigger-mappings` route):

```python
@router.get(
    "/document-tagging-config",
    response_model=DocumentTaggingConfigResponse,
    summary="Get the active document AI tagging configuration with masked API key (admin)",
)
async def get_document_tagging_config(
    db: DBSession,
    current_user: AdminUser,
) -> DocumentTaggingConfigResponse:
    data = await get_active_document_tagging_settings(db)
    return DocumentTaggingConfigResponse.from_dict_masked(data)


@router.patch(
    "/document-tagging-config",
    response_model=DocumentTaggingConfigResponse,
    summary="Update the document AI tagging configuration (admin)",
)
async def update_document_tagging_config(
    payload: DocumentTaggingConfigUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> DocumentTaggingConfigResponse:
    current_settings = await get_active_document_tagging_settings(db)
    new_settings = payload.model_dump()

    changed_keys = []
    for k, v in new_settings.items():
        if k == "DOCUMENT_TAGGING_API_KEY":
            if v not in ("", MASKED_PASSWORD_PLACEHOLDER) and v != current_settings.get(k):
                changed_keys.append(k)
            continue
        if current_settings.get(k) != v:
            changed_keys.append(k)

    await set_active_document_tagging_settings(db, new_settings)

    await write_audit_log(
        db,
        action="system_config.document_tagging_updated",
        resource_type="system_config",
        actor_id=current_user.id,
        resource_id=None,
        payload={"updated_keys": changed_keys},
    )

    final_settings = await get_active_document_tagging_settings(db)
    return DocumentTaggingConfigResponse.from_dict_masked(final_settings)
```

- [ ] **Step 4: Verify — live round-trip through the API**

```bash
docker compose restart web
until curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs | grep -q 200; do sleep 1; done

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")

echo "--- before ---"
curl -s http://localhost:8000/api/v1/admin/document-tagging-config -H "Authorization: Bearer $TOKEN"

echo
echo "--- set a URL ---"
curl -s -X PATCH http://localhost:8000/api/v1/admin/document-tagging-config -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"DOCUMENT_TAGGING_URL": "https://example.com/process-document", "DOCUMENT_TAGGING_API_KEY": ""}'

echo
echo "--- PATCH again with blank key, unrelated URL edit — key must have nothing to blank since none was set yet; now set a real key ---"
curl -s -X PATCH http://localhost:8000/api/v1/admin/document-tagging-config -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"DOCUMENT_TAGGING_URL": "https://example.com/process-document", "DOCUMENT_TAGGING_API_KEY": "real-key-123"}'

echo
echo "--- PATCH with masked placeholder as key (simulates a settings-form round trip) — real key must survive ---"
curl -s -X PATCH http://localhost:8000/api/v1/admin/document-tagging-config -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"DOCUMENT_TAGGING_URL": "https://example.com/process-document", "DOCUMENT_TAGGING_API_KEY": "********"}'

echo
docker compose exec -T db psql -U ists -d ists -c "SELECT value->>'DOCUMENT_TAGGING_API_KEY' FROM system_config WHERE key='document_tagging_config';"
```

Expected: the final `psql` query prints `real-key-123` — proving the masked-placeholder PATCH did not overwrite the real key (matches the SMTP fix's verified behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/document_tagging_config.py backend/app/schemas/admin.py backend/app/api/v1/admin.py
git commit -m "feat: add admin-configurable document tagging service settings"
```

---

### Task 4: `tag_document` Celery task

**Files:**
- Create: `backend/app/tasks/documents.py`
- Modify: `backend/app/celery_app.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `document_tag_service` (Task 2), `get_active_document_tagging_settings` (Task 3), `get_storage_backend` from `app.core.storage` (existing), `write_audit_log` (existing).
- Produces: Celery task `app.tasks.documents.tag_document(document_id: str) -> dict`, dispatched via `.delay(document_id)` — used by Task 5 (upload) and Task 6 (retry endpoint).

- [ ] **Step 1: Write the task module**

```python
"""
Celery tasks: documents queue.

tag_document(document_id) — POSTs a document's file to the admin-configured
AI tagging service and stores the structured response in document_tags.
See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md.
"""

import asyncio
import uuid

import httpx
import structlog

from app.celery_app import celery

log = structlog.get_logger(__name__)

# The response's fixed category keys — every value across all of these,
# plus summary and department, gets flattened into search_text.
_CATEGORY_KEYS = [
    "category_01_metadata",
    "category_02_primary_subject",
    "category_03_technical_methods",
    "category_04_nlp_ai_models",
    "category_05_application_domain",
    "category_06_system_architecture",
    "category_07_statistical_mathematical",
    "category_08_semantic_conceptual",
    "category_09_long_tail_phrases",
]


def _build_search_text(payload: dict) -> str:
    """Flatten summary + department + every category tag into one lowercase, space-joined string."""
    parts: list[str] = []
    if payload.get("summary"):
        parts.append(str(payload["summary"]))
    if payload.get("department"):
        parts.append(str(payload["department"]))
    for key in _CATEGORY_KEYS:
        for value in payload.get(key) or []:
            parts.append(str(value))
    return " ".join(parts).lower()


async def _tag_document_async(document_id: str) -> dict:
    from app.database import async_session_factory
    from app.core.document_tagging_config import get_active_document_tagging_settings
    from app.core.storage import get_storage_backend
    from app.models.document import Document
    from app.models.document_tag import DocumentTagStatus
    from app.services import document_tag_service
    from sqlalchemy import select

    doc_uuid = uuid.UUID(document_id)

    async with async_session_factory() as db:
        doc = await db.get(Document, doc_uuid)
        if doc is None:
            log.error("tag_document_not_found", document_id=document_id)
            return {"status": "error", "reason": "document_not_found"}

        settings_dict = await get_active_document_tagging_settings(db)
        url = settings_dict.get("DOCUMENT_TAGGING_URL", "")

        if not url:
            log.info("tag_document_not_configured", document_id=document_id)
            await document_tag_service.mark_tag_result(
                doc_uuid, db,
                status=DocumentTagStatus.failed,
                error_message="Document tagging is not configured",
            )
            await db.commit()
            return {"status": "skipped", "reason": "not_configured"}

        storage = get_storage_backend()
        storage_ref = storage.download_url(doc.storage_path, ttl=300)

        if storage_ref.startswith("http://") or storage_ref.startswith("https://"):
            async with httpx.AsyncClient(timeout=60) as client:
                file_resp = await client.get(storage_ref)
                file_resp.raise_for_status()
                file_bytes = file_resp.content
        else:
            with open(storage_ref, "rb") as f:
                file_bytes = f.read()

        headers = {}
        api_key = settings_dict.get("DOCUMENT_TAGGING_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                url,
                files={"file": (doc.filename, file_bytes, doc.mime_type)},
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()

        search_text = _build_search_text(result)
        await document_tag_service.mark_tag_result(
            doc_uuid, db,
            status=DocumentTagStatus.ok,
            document_type=result.get("document_type"),
            summary=result.get("summary"),
            department=result.get("department"),
            raw_response=result,
            search_text=search_text,
        )
        await db.commit()

    log.info("tag_document_complete", document_id=document_id)
    return {"status": "ok", "document_id": document_id}


async def _mark_tagging_permanently_failed(document_id: str, error_msg: str) -> None:
    from app.database import async_session_factory
    from app.models.document_tag import DocumentTagStatus
    from app.services import document_tag_service
    from app.services.audit_service import write_audit_log

    doc_uuid = uuid.UUID(document_id)
    async with async_session_factory() as db:
        await document_tag_service.mark_tag_result(
            doc_uuid, db,
            status=DocumentTagStatus.failed,
            error_message=error_msg,
        )
        await write_audit_log(
            db,
            action="document.tagging_failed",
            resource_type="document",
            resource_id=doc_uuid,
            payload={"error": error_msg},
        )
        await db.commit()


@celery.task(
    name="app.tasks.documents.tag_document",
    queue="documents",
    bind=True,
    max_retries=3,
)
def tag_document(self, document_id: str) -> dict:
    """Tag a document via the external AI service. Retries on failure; see module docstring."""
    log.info("tag_document_starting", document_id=document_id, attempt=self.request.retries + 1)

    try:
        return asyncio.run(_tag_document_async(document_id))
    except Exception as exc:
        retries = self.request.retries
        is_final = retries >= self.max_retries

        if is_final:
            log.error(
                "tag_document_permanently_failed",
                document_id=document_id,
                retries=retries,
                error=str(exc),
            )
            asyncio.run(_mark_tagging_permanently_failed(document_id, str(exc)))
            return {"status": "permanently_failed", "document_id": document_id, "error": str(exc)}

        countdown = 60 * (2 ** retries)
        log.warning(
            "tag_document_retrying",
            document_id=document_id,
            error=str(exc),
            retry_number=retries + 1,
            countdown_seconds=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
```

- [ ] **Step 2: Register the `documents` queue in `backend/app/celery_app.py`**

Change the `task_routes` block:

```python
    task_routes={
        "app.tasks.feeds.*": {"queue": "feeds"},
        "app.tasks.notifications.*": {"queue": "notifications"},
        "app.tasks.maintenance.*": {"queue": "maintenance"},
        "app.tasks.documents.*": {"queue": "documents"},
    },
```

Also update the module docstring's queue list at the top of the file (lines 7–10) to add:
```
  documents     — AI document-tagging tasks
```

- [ ] **Step 3: Add the `documents` queue to the worker in `docker-compose.yml`**

Change:
```yaml
    command: >
      celery -A app.celery_app worker
      -Q feeds,notifications,maintenance
      --loglevel=info
      --pool=solo
```
to:
```yaml
    command: >
      celery -A app.celery_app worker
      -Q feeds,notifications,maintenance,documents
      --loglevel=info
      --pool=solo
```

- [ ] **Step 4: Verify — apply the compose change and confirm the task runs against a local mock server**

```bash
docker compose up -d worker
docker compose logs worker --tail=20
```
Expected: worker starts cleanly, no errors, celery banner shows the `documents` queue.

Start a throwaway local mock tagging server on the host, then point the app at it (using `host.docker.internal`, which the `worker`/`web` containers can already reach on Docker Desktop for Windows):

```bash
python -c "
import http.server, json, threading

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        self.rfile.read(length)
        body = json.dumps({
            'document_type': 'standard',
            'summary': 'Mock summary for verification',
            'department': 'Quality Control',
            'category_01_metadata': ['Mock Tag A'],
            'category_02_primary_subject': ['Mock Tag B'],
            'category_03_technical_methods': [],
            'category_04_nlp_ai_models': [],
            'category_05_application_domain': [],
            'category_06_system_architecture': [],
            'category_07_statistical_mathematical': [],
            'category_08_semantic_conceptual': [],
            'category_09_long_tail_phrases': [],
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

server = http.server.HTTPServer(('0.0.0.0', 8999), Handler)
print('mock server listening on :8999')
server.serve_forever()
" &
MOCK_PID=$!
sleep 1

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
curl -s -X PATCH http://localhost:8000/api/v1/admin/document-tagging-config -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"DOCUMENT_TAGGING_URL": "http://host.docker.internal:8999/process-document", "DOCUMENT_TAGGING_API_KEY": ""}'
echo

docker compose exec -T db psql -U ists -d ists -c "SELECT id FROM documents LIMIT 1;"
```

Substitute the printed document UUID for `<DOC_ID>` below:

```bash
docker compose exec -T web python -c "
import asyncio, uuid
from app.database import async_session_factory
from app.services import document_tag_service
from app.models.document_tag import DocumentTagStatus
from app.tasks.documents import _tag_document_async

DOC_ID = '<DOC_ID>'

async def main():
    async with async_session_factory() as db:
        await document_tag_service.create_pending_tag(uuid.UUID(DOC_ID), db)
        await db.commit()

    result = await _tag_document_async(DOC_ID)
    print('task result:', result)

    async with async_session_factory() as db:
        tag = await document_tag_service.get_tag_for_document(uuid.UUID(DOC_ID), db)
        print('final status:', tag.status, 'summary:', tag.summary, 'search_text:', tag.search_text)

asyncio.run(main())
"
kill $MOCK_PID
docker compose exec -T db psql -U ists -d ists -c "DELETE FROM document_tags WHERE document_id='<DOC_ID>';"
```

Expected: `task result: {'status': 'ok', 'document_id': '<DOC_ID>'}` and `final status: DocumentTagStatus.ok summary: Mock summary for verification search_text: mock summary for verification quality control mock tag a mock tag b`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/documents.py backend/app/celery_app.py docker-compose.yml
git commit -m "feat: add tag_document Celery task and documents queue"
```

---

### Task 5: Wire document upload to tagging

**Files:**
- Modify: `backend/app/services/document_service.py`

**Interfaces:**
- Consumes: `document_tag_service.create_pending_tag` (Task 2), `tag_document` task (Task 4).

- [ ] **Step 1: Add the pending-tag-row creation and task dispatch**

In `upload_document()`, add the import at the top of the file:

```python
from app.services import document_tag_service
```

Insert a new step between the existing "7. Insert Document row" block and "8. Audit log" block (i.e. right after the existing `await db.flush()  # get doc.id before audit/notifications` line):

```python
    # 7b. Create the pending document_tags row (AI tagging runs async — see
    # tag_document task, dispatched below after commit)
    await document_tag_service.create_pending_tag(doc.id, db)
```

Then, right after the existing `# 10. Enqueue email notifications to distribution lists` block (after the `send_email_notification.delay(...)` call, still before the `log.info("document.uploaded", ...)` call), add:

```python
    # 11. Dispatch AI tagging (async — see tag_document task)
    from app.tasks.documents import tag_document
    tag_document.delay(str(doc.id))
```

- [ ] **Step 2: Verify — upload a real document and confirm a pending tag row appears**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
STD_ID=$(curl -s "http://localhost:8000/api/v1/standards?page_size=1" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")

printf '%%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%%%EOF\nTASK5VERIFY' > /tmp/task5_test.pdf

RESP=$(curl -s -X POST "http://localhost:8000/api/v1/standards/$STD_ID/documents" -H "Authorization: Bearer $TOKEN" -F "file=@/tmp/task5_test.pdf;type=application/pdf")
echo "$RESP"
DOC_ID=$(echo "$RESP" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

sleep 2
docker compose exec -T db psql -U ists -d ists -c "SELECT status, error_message FROM document_tags WHERE document_id='$DOC_ID';"
```

Expected: a `document_tags` row exists for the new document. Since no real tagging URL is configured at this point in the plan (Task 3's test config used a since-killed mock server), `status` should be `failed` with `error_message` either `"Document tagging is not configured"` (if the URL got cleared) or a connection error (if it's still pointed at the dead mock server) — either way, this proves the row was created and the task ran, without the upload itself failing (the `curl` upload command above must have returned `201` with the document JSON).

Clean up:
```bash
docker compose exec -T db psql -U ists -d ists -c "DELETE FROM documents WHERE id='$DOC_ID';"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/document_service.py
git commit -m "feat: dispatch AI tagging on every document upload"
```

---

### Task 6: Retry endpoint and tag data in API responses

**Files:**
- Modify: `backend/app/schemas/document.py`
- Modify: `backend/app/api/v1/documents.py`

**Interfaces:**
- Consumes: `document_tag_service.get_tag_for_document`, `get_tags_for_documents`, `reset_tag_to_pending` (Task 2), `tag_document` task (Task 4).
- Produces: `DocumentTagResponse` schema, `DocumentResponse.tags` field, `POST /api/v1/documents/{document_id}/retag` endpoint — used by the frontend (Tasks 8, 10).

- [ ] **Step 1: Add `DocumentTagResponse` and extend `DocumentResponse` in `backend/app/schemas/document.py`**

Add after the imports, before `DocumentResponse`:

```python
from typing import Any


class DocumentTagResponse(BaseModel):
    """AI-generated tag data for one document version."""

    status: str  # "pending" | "ok" | "failed"
    document_type: str | None
    summary: str | None
    department: str | None
    raw_response: dict[str, Any] | None
    error_message: str | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
```

Add a `tags` field to `DocumentResponse`:

```python
class DocumentResponse(BaseModel):
    """Full document metadata — returned in list and after upload."""

    id: uuid.UUID
    standard_id: uuid.UUID
    version_number: int
    filename: str
    file_size_bytes: int
    sha256_checksum: str
    mime_type: str
    change_notes: str | None
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    is_current: bool
    tags: DocumentTagResponse | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Populate `tags` in `backend/app/api/v1/documents.py`**

Add imports at the top of the file:

```python
from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.schemas.document import DocumentDownloadResponse, DocumentResponse, DocumentTagResponse
from app.services import document_tag_service, document_service
```

(This replaces the existing `from app.schemas.document import DocumentDownloadResponse, DocumentResponse` line and the existing `from app.services import document_service` line — merge them as shown so there's exactly one import per module.)

Update `list_documents` to attach tags:

```python
async def list_documents(
    standard_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[DocumentResponse]:
    """
    Return all uploaded document versions for a standard, newest first.
    Returns 404 if the standard does not exist.
    """
    docs = await document_service.list_documents(standard_id, db)

    # Manual pagination on the in-memory list (documents per standard are few)
    total = len(docs)
    offset = (page - 1) * page_size
    paged = docs[offset : offset + page_size]

    tag_map = await document_tag_service.get_tags_for_documents([d.id for d in paged], db)
    items = []
    for d in paged:
        resp = DocumentResponse.model_validate(d)
        tag = tag_map.get(d.id)
        resp.tags = DocumentTagResponse.model_validate(tag) if tag else None
        items.append(resp)

    return Page[DocumentResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
```

Update `upload_document`'s return to attach the tag too — replace its final line `return DocumentResponse.model_validate(doc)` with:

```python
    resp = DocumentResponse.model_validate(doc)
    tag = await document_tag_service.get_tag_for_document(doc.id, db)
    resp.tags = DocumentTagResponse.model_validate(tag) if tag else None
    return resp
```

- [ ] **Step 3: Add the retry endpoint**

Add after the existing `upload_document` route, before the `# ── Standalone /documents/{document_id}/* ──` section comment:

```python
@router.post(
    "/documents/{document_id}/retag",
    response_model=DocumentResponse,
    summary="Re-run AI tagging for a document (manager+)",
)
async def retag_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: ManagerOrAdminUser,
) -> DocumentResponse:
    """
    Reset a document's tag status to pending and re-dispatch tagging.

    Available regardless of current tag status (not just failed ones).
    Returns 404 if the document doesn't exist, or if it has never been
    tagged (documents uploaded before this feature shipped have no tag row —
    re-uploading is the only way to get one, since there's nothing to reset).
    """
    from app.tasks.documents import tag_document

    doc = await db.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document")

    tag = await document_tag_service.reset_tag_to_pending(document_id, db)
    await db.commit()

    tag_document.delay(str(document_id))

    resp = DocumentResponse.model_validate(doc)
    resp.tags = DocumentTagResponse.model_validate(tag)
    return resp
```

Note: `document_tag_service.reset_tag_to_pending` already raises `NotFoundError("DocumentTag")` if there's no tag row — the explicit `db.get(Document, ...)` check above it exists so a genuinely-nonexistent document reports "Document" rather than the more confusing "DocumentTag" in that error.

- [ ] **Step 4: Verify — full retag round trip**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
STD_ID=$(curl -s "http://localhost:8000/api/v1/standards?page_size=1" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")

printf '%%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%%%EOF\nTASK6VERIFY' > /tmp/task6_test.pdf
RESP=$(curl -s -X POST "http://localhost:8000/api/v1/standards/$STD_ID/documents" -H "Authorization: Bearer $TOKEN" -F "file=@/tmp/task6_test.pdf;type=application/pdf")
echo "upload response includes tags field:"
echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); print('tags' in d, d.get('tags'))"
DOC_ID=$(echo "$RESP" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "--- list endpoint includes tags ---"
curl -s "http://localhost:8000/api/v1/standards/$STD_ID/documents" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print([('tags' in i) for i in d['items']])"

echo "--- retag ---"
curl -s -w "\nHTTP:%{http_code}\n" -X POST "http://localhost:8000/api/v1/documents/$DOC_ID/retag" -H "Authorization: Bearer $TOKEN"

echo "--- retag a nonexistent document returns 404 ---"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://localhost:8000/api/v1/documents/00000000-0000-0000-0000-000000000000/retag" -H "Authorization: Bearer $TOKEN"

docker compose exec -T db psql -U ists -d ists -c "DELETE FROM documents WHERE id='$DOC_ID';"
```

Expected: upload response has `tags` key with a dict (`status: "pending"` or already resolved), the list endpoint's items all have a `tags` key, the retag call returns `200` with a `tags.status` of `"pending"`, and the nonexistent-document retag returns `404`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/document.py backend/app/api/v1/documents.py
git commit -m "feat: add document retag endpoint and include tags in document responses"
```

---

### Task 7: Tag-based search in Standards list

**Files:**
- Modify: `backend/app/services/standard_service.py`

**Interfaces:**
- Consumes: `Document` (existing), `DocumentTag` (Task 1).

- [ ] **Step 1: Add the join-based search condition to `list_standards`**

Add imports at the top of the file:

```python
from app.models.document import Document
from app.models.document_tag import DocumentTag
```

In `list_standards()`, replace the `if search:` block:

```python
    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Standard.iso_reference.ilike(search_term),
                Standard.title.ilike(search_term),
                Standard.tc_committee.ilike(search_term),
            )
        )
```

with:

```python
    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Standard.iso_reference.ilike(search_term),
                Standard.title.ilike(search_term),
                Standard.tc_committee.ilike(search_term),
                Standard.id.in_(
                    select(Document.standard_id)
                    .join(DocumentTag, DocumentTag.document_id == Document.id)
                    .where(DocumentTag.search_text.ilike(search_term))
                ),
            )
        )
```

- [ ] **Step 2: Add the equivalent to `get_grouped_standards`**

`_matches_filters` operates purely in-memory on already-loaded `Standard` objects with no per-call DB access, so a set of matching standard IDs must be precomputed once before the grouping loop.

Update `_matches_filters`'s signature and search check:

```python
def _matches_filters(
    standard: Standard,
    *,
    search: str | None,
    status: StandardStatus | None,
    tc_committee: str | None,
    stage: str | None,
    is_purchased: bool | None,
    tag_matched_ids: set[uuid.UUID] | None = None,
) -> bool:
    """Evaluate the same filter semantics as list_standards' SQL conditions, in Python."""
    if search:
        needle = search.strip().lower()
        haystacks = [standard.iso_reference, standard.title, standard.tc_committee]
        text_match = any(needle in h.lower() for h in haystacks if h)
        tag_match = tag_matched_ids is not None and standard.id in tag_matched_ids
        if not (text_match or tag_match):
            return False
    if status is not None and standard.status != status:
        return False
    if tc_committee is not None and standard.tc_committee != tc_committee:
        return False
    if not _stage_matches(standard.stage_code, stage):
        return False
    if is_purchased is not None and standard.is_purchased != is_purchased:
        return False
    return True
```

In `get_grouped_standards()`, right after the existing `all_standards = list(result.scalars().all())` line, add:

```python
    tag_matched_ids: set[uuid.UUID] | None = None
    if search:
        search_term = f"%{search.strip()}%"
        tag_result = await db.execute(
            select(Document.standard_id)
            .join(DocumentTag, DocumentTag.document_id == Document.id)
            .where(DocumentTag.search_text.ilike(search_term))
            .distinct()
        )
        tag_matched_ids = {row[0] for row in tag_result.all()}
```

Then update the `_matches_filters(...)` call inside the grouping loop to pass it through:

```python
        if not _matches_filters(
            primary,
            search=search,
            status=status,
            tc_committee=tc_committee,
            stage=stage,
            is_purchased=is_purchased,
            tag_matched_ids=tag_matched_ids,
        ):
```

- [ ] **Step 3: Verify — search by a tag term that isn't in any standard's title**

Set up a document with a searchable tag directly (bypassing the external service, since the goal here is testing the search query, not the tagging pipeline):

```bash
docker compose exec -T db psql -U ists -d ists -c "SELECT id, iso_reference FROM standards LIMIT 1;"
```

Substitute the printed standard ID for `<STD_ID>`:

```bash
docker compose exec -T web python -c "
import asyncio, uuid
from app.database import async_session_factory
from app.models.document import Document
from app.models.document_tag import DocumentTag, DocumentTagStatus

STD_ID = uuid.UUID('<STD_ID>')

async def main():
    async with async_session_factory() as db:
        doc = Document(
            standard_id=STD_ID, version_number=999, filename='search_test.pdf',
            storage_path='test/search_test.pdf', file_size_bytes=1, sha256_checksum='0'*64,
            mime_type='application/pdf', uploaded_by=(await db.execute(__import__('sqlalchemy').select(__import__('app.models.user', fromlist=['User']).User.id).limit(1))).scalar_one(),
            is_current=False,
        )
        db.add(doc)
        await db.flush()
        tag = DocumentTag(
            document_id=doc.id, status=DocumentTagStatus.ok,
            search_text='cosine similarity thread profile analysis',
        )
        db.add(tag)
        await db.commit()
        print('created document', doc.id, 'for standard', STD_ID)

asyncio.run(main())
"

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")

echo "--- flat search (list_standards path) ---"
curl -s "http://localhost:8000/api/v1/standards?search=cosine+similarity&grouped=false" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('total:', d['total'], [i['iso_reference'] for i in d['items']])"

echo "--- grouped search (get_grouped_standards path) ---"
curl -s "http://localhost:8000/api/v1/standards?search=cosine+similarity&grouped=true" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('total:', d['total'], [i['iso_reference'] for i in d['items']])"

docker compose exec -T db psql -U ists -d ists -c "DELETE FROM documents WHERE version_number=999 AND filename='search_test.pdf';"
```

Expected: both searches return `total: 1` and include `<STD_ID>`'s `iso_reference`, even though "cosine similarity" appears nowhere in that standard's title/iso_reference/committee — proving the tag join works in both code paths.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/standard_service.py
git commit -m "feat: match document tags in Standards search"
```

---

### Task 8: Frontend API clients

**Files:**
- Modify: `frontend/src/api/documents.ts`
- Create: `frontend/src/api/documentTagging.ts`

**Interfaces:**
- Produces: `DocumentTag` interface, `Document.tags` field, `retagDocument(documentId)` in `documents.ts`; `getDocumentTaggingConfig()`, `updateDocumentTaggingConfig()` in `documentTagging.ts` — used by Tasks 9, 10.

- [ ] **Step 1: Extend `frontend/src/api/documents.ts`**

Add after the existing `DocumentDownloadResponse` interface:

```typescript
export interface DocumentTag {
  status: "pending" | "ok" | "failed";
  document_type: string | null;
  summary: string | null;
  department: string | null;
  raw_response: Record<string, unknown> | null;
  error_message: string | null;
  completed_at: string | null;
}
```

Add `tags` to the `Document` interface:

```typescript
export interface Document {
  id: string;
  standard_id: string;
  version_number: number;
  filename: string;
  file_size_bytes: number;
  sha256_checksum: string;
  mime_type: string;
  change_notes: string | null;
  uploaded_by: string;
  uploaded_at: string;
  is_current: boolean;
  tags: DocumentTag | null;
}
```

Add a new function after `deleteDocument`:

```typescript
/** Reset a document's AI tagging to pending and re-dispatch it (manager+). */
export async function retagDocument(documentId: string): Promise<Document> {
  const { data } = await api.post<Document>(`/api/v1/documents/${documentId}/retag`);
  return data;
}
```

- [ ] **Step 2: Create `frontend/src/api/documentTagging.ts`**

```typescript
import api from "@/lib/axios";

export interface DocumentTaggingConfig {
  DOCUMENT_TAGGING_URL: string;
  DOCUMENT_TAGGING_API_KEY: string;
}

export async function getDocumentTaggingConfig(): Promise<DocumentTaggingConfig> {
  const { data } = await api.get<DocumentTaggingConfig>("/api/v1/admin/document-tagging-config");
  return data;
}

export async function updateDocumentTaggingConfig(
  payload: DocumentTaggingConfig
): Promise<DocumentTaggingConfig> {
  const { data } = await api.patch<DocumentTaggingConfig>(
    "/api/v1/admin/document-tagging-config",
    payload
  );
  return data;
}
```

- [ ] **Step 3: Verify — typecheck**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: exits with no output/errors (existing files that import `Document` don't reference a `tags` field yet, so adding an optional-looking-but-required field... note `tags: DocumentTag | null` is required, not optional, matching the backend's `tags: DocumentTagResponse | None = None` which always serializes to a key, even if `null`). No existing code constructs a `Document` object literal (it's only ever received from API responses), so this won't break existing call sites.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/api/documentTagging.ts
git commit -m "feat: add frontend API clients for document tags and tagging config"
```

---

### Task 9: Admin "Document Tagging" settings page

**Files:**
- Create: `frontend/src/pages/DocumentTaggingConfigPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/Layout.tsx`

**Interfaces:**
- Consumes: `getDocumentTaggingConfig`, `updateDocumentTaggingConfig` (Task 8).

- [ ] **Step 1: Write the page**

Same shape as `frontend/src/pages/SMTPConfigPage.tsx`, including its masked-secret fix (don't preload the masked key into editable state):

```tsx
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tag, Save, Loader2, Info } from "lucide-react";
import { getDocumentTaggingConfig, updateDocumentTaggingConfig } from "@/api/documentTagging";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function DocumentTaggingConfigPage() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const { data: config, isLoading } = useQuery({
    queryKey: ["document-tagging-config"],
    queryFn: getDocumentTaggingConfig,
  });

  // API key is intentionally excluded here — see SMTPConfigPage.tsx for why
  // preloading a masked secret into an editable field is unsafe.
  useEffect(() => {
    if (config) {
      setUrl(config.DOCUMENT_TAGGING_URL);
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: updateDocumentTaggingConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document-tagging-config"] });
      setSuccessMsg("Document tagging configuration saved successfully!");
      setErrorMsg(null);
      setApiKey("");
      setTimeout(() => setSuccessMsg(null), 5000);
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to save configuration");
      setSuccessMsg(null);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) {
      setErrorMsg("Please enter the tagging service URL.");
      return;
    }
    saveMutation.mutate({
      DOCUMENT_TAGGING_URL: url,
      DOCUMENT_TAGGING_API_KEY: apiKey,
    });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Tag className="h-6 w-6 text-teal-400" />
          Document Tagging
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure the external AI service that tags uploaded documents for search.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tagging Service Configuration</CardTitle>
          <CardDescription>
            Every document upload is sent here in the background; the response is stored and made searchable.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4 py-4">
              <div className="h-4 bg-white/5 rounded w-1/4 animate-pulse"></div>
              <div className="h-10 bg-white/5 rounded animate-pulse"></div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {errorMsg && (
                <div className="border border-red-500/20 bg-red-500/10 text-red-400 p-3 rounded-lg text-sm">
                  {errorMsg}
                </div>
              )}
              {successMsg && (
                <div className="border border-teal-500/20 bg-teal-500/10 text-teal-300 p-3 rounded-lg text-sm">
                  {successMsg}
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="tagging-url">Tagging Service URL *</Label>
                <Input
                  id="tagging-url"
                  placeholder="https://your-tagging-service.example.com/process-document"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="tagging-key">API Key (optional)</Label>
                <Input
                  id="tagging-key"
                  type="password"
                  placeholder={config?.DOCUMENT_TAGGING_API_KEY ? "Leave blank to keep current key" : "Enter API key"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>

              <div className="flex justify-end pt-4">
                <Button
                  type="submit"
                  disabled={saveMutation.isPending}
                  className="gap-2 bg-teal-600 hover:bg-teal-700"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save Configuration
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      <div className="rounded-lg border border-teal-500/10 bg-teal-500/5 px-4 py-3 flex gap-3 text-sm text-teal-300">
        <Info className="h-5 w-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold">If left unconfigured</p>
          <p className="opacity-90 mt-0.5">
            Document uploads still work normally — tagging is simply skipped until a URL is set here.
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire up routing in `frontend/src/App.tsx`**

Add the import alongside the existing page imports:

```typescript
import { DocumentTaggingConfigPage } from "@/pages/DocumentTaggingConfigPage";
```

Add the route inside the `<Route element={<AdminLayout />}>` block, alongside `/admin/smtp-config`:

```typescript
                  <Route path="/admin/document-tagging" element={<DocumentTaggingConfigPage />} />
```

- [ ] **Step 3: Add the nav entry in `frontend/src/components/Sidebar.tsx`**

Add `Tag` to the lucide-react import list, and add a nav item after `"SMTP Settings"`:

```typescript
  { label: "Document Tagging", href: "/admin/document-tagging", icon: Tag, adminOnly: true },
```

- [ ] **Step 4: Add the page title in `frontend/src/components/Layout.tsx`**

Add alongside the existing `"/admin/smtp-config": "SMTP Settings"` entry:

```typescript
  "/admin/document-tagging": "Document Tagging",
```

- [ ] **Step 5: Verify — typecheck and live check**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: no errors.

```bash
docker compose logs frontend --tail=20
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/src/pages/DocumentTaggingConfigPage.tsx
```
Expected: `200`, and no new errors in the Vite dev server log.

Then log in at `http://localhost:5173` as `admin@ists.local` / `Admin1234!`, confirm "Document Tagging" appears in the sidebar under the admin section, click into it, and confirm the page loads with the URL field populated from Task 3's saved config (if that config still exists — otherwise it'll show blank, which is also correct).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DocumentTaggingConfigPage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/components/Layout.tsx
git commit -m "feat: add Document Tagging admin settings page"
```

---

### Task 10: Display tags and retry action in the Documents tab

**Files:**
- Modify: `frontend/src/pages/StandardDetailPage.tsx`

**Interfaces:**
- Consumes: `Document.tags` (Task 8), `retagDocument` (Task 8), `Badge`/`StatusBadge` from `@/components/ui/badge` (existing).

- [ ] **Step 1: Import `retagDocument` and `Badge`**

Add `retagDocument` to the existing import from `@/api/documents`:

```typescript
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  retagDocument,
  downloadDocumentBlob,
  ...
```

Add `Badge` to the existing import from `@/components/ui/badge` (if not already imported — check the top of the file; `StatusBadge` alone may currently be imported elsewhere, add `Badge` alongside it in `DocumentsTab`'s imports if it's a separate import line, otherwise add `import { Badge } from "@/components/ui/badge";` near the other UI component imports).

Add `RefreshCw` to the existing `lucide-react` import for the retry button icon.

- [ ] **Step 2: Add a retag mutation inside `DocumentsTab`**

Right after the existing `deleteMutation` definition:

```tsx
  const [retaggingId, setRetaggingId] = useState<string | null>(null);
  const retagMutation = useMutation({
    mutationFn: (docId: string) => retagDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
      setRetaggingId(null);
    },
    onError: () => {
      setRetaggingId(null);
    },
  });
```

- [ ] **Step 3: Render tag status/content under each document row**

Insert this block right after the existing metadata `<div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">...</div>` (the one showing file size / uploaded time / change notes) and before the closing `</div>` of the "File info" column:

```tsx
                  {doc.tags && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {doc.tags.status === "pending" && (
                        <span className="text-[10px] text-muted-foreground italic">Tagging pending…</span>
                      )}
                      {doc.tags.status === "failed" && (
                        <>
                          <span className="text-[10px] text-red-400">Tagging failed</span>
                          {(isAdmin || isManager) && (
                            <button
                              onClick={() => {
                                setRetaggingId(doc.id);
                                retagMutation.mutate(doc.id);
                              }}
                              disabled={retagMutation.isPending && retaggingId === doc.id}
                              className="inline-flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
                            >
                              {retagMutation.isPending && retaggingId === doc.id ? (
                                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-2.5 w-2.5" />
                              )}
                              Retry tagging
                            </button>
                          )}
                        </>
                      )}
                      {doc.tags.status === "ok" && (
                        <>
                          {doc.tags.department && (
                            <Badge variant="secondary" className="text-[9px] py-0 px-1.5">
                              {doc.tags.department}
                            </Badge>
                          )}
                          {doc.tags.summary && (
                            <p className="text-[10px] text-muted-foreground/80 italic truncate max-w-full basis-full">
                              {doc.tags.summary}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
```

Note: this uses `Loader2` (already imported) and `RefreshCw`/`Badge` (added in Step 1). `isAdmin`/`isManager` are already in scope in `DocumentsTab` (destructured from `useAuth()` at the top of the component).

- [ ] **Step 4: Verify — typecheck and live check**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: no errors.

Then, with the full stack running and a tagging URL configured (reuse the mock server from Task 4's verification, or leave unconfigured to see the `failed` + "Retry tagging" state), upload a document via the UI on a standard's detail page and confirm:
- Immediately after upload: "Tagging pending…" appears under the file row.
- After a few seconds (refresh the page or wait for the existing document list to refetch): either the summary/department badge appears (`status=ok`) or "Tagging failed" + a working "Retry tagging" link appears (`status=failed`), matching whichever the configured tagging URL produces.
- Clicking "Retry tagging" flips the row back to "Tagging pending…".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/StandardDetailPage.tsx
git commit -m "feat: show AI tags and retry action in the Documents tab"
```
