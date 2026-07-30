# Draft-Stage Purchase and Upload Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block document upload and purchase for standards at a pre-publication ISO stage, and allow purchase only once a document has been uploaded.

**Architecture:** The backend owns the rules. A dependency-free helper decides whether a stage code is a draft; a service function derives five read-only fields that the API returns on every `StandardDetail` response; two guards enforce the same rules on the write paths. The frontend reads the derived fields and contains no ISO stage logic, so a future UI rebuild inherits the rules unchanged.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, React 19 + TypeScript, TanStack Query v5, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-07-30-draft-stage-purchase-upload-gating-design.md`

## Global Constraints

- **There is no test framework in this repository.** `pytest` is listed in `backend/requirements-dev.txt` but is **not installed in the runtime container** (`docker compose exec -T web python -c "import pytest"` → `ModuleNotFoundError`), and there is no `conftest.py` or any test file anywhere in `backend/`. Do not write `pytest` tests and do not attempt to stand up test infrastructure — it is out of scope. Verification in this plan uses executable assertion scripts (`python -c`) for pure functions and `curl` + `psql` against the running stack for behaviour. Every task still ends with a verification step that must be *run* and must *pass* before committing.
- **Draft rule:** a standard is a draft when the major part of `stage_code` is `< 60`. `stage_code = None` → **not** a draft (fail open).
- **Document count** means documents with `is_current = True` only. Soft-delete sets `is_current = False`.
- **Derived fields must never be ORM properties on `Standard`.** A lazy attribute access from synchronous code raises `sqlalchemy.exc.MissingGreenlet` under async SQLAlchemy — this exact bug was fixed in commit `0211de5`. `document_count` requires a `COUNT` query, so it is computed by an `async` service function that receives the session.
- **Do not modify** `rss_feeds`, feed polling, the API-key pool, or any Alembic migration. This change is schema-free — no new columns, no migration.
- The local stack must be running for verification: `docker compose up -d`. The database currently holds the restored production snapshot (3,283 standards: 249 drafts, 3,034 published, 8 with documents, 2 purchased).
- Reason strings, verbatim:
  - draft: `"Not available — standard is still at draft stage ({stage_code} {stage_name}). Available once published."`
  - no document: `"Upload the standard document before marking it as purchased."`

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/app/core/iso_stages.py` | create | Decide whether an ISO stage code is pre-publication. Pure, no imports from the app. |
| `backend/app/schemas/standard.py` | modify | Add five derived fields to `StandardDetail`. |
| `backend/app/services/standard_service.py` | modify | Add `get_purchasability()`; guard `purchase_standard()`. |
| `backend/app/api/v1/standards.py` | modify | Populate derived fields at the three `StandardDetail` construction sites. |
| `backend/app/api/v1/documents.py` | modify | Reject upload for a draft standard. |
| `frontend/src/api/standards.ts` | modify | Add the five fields to the `Standard` type. |
| `frontend/src/pages/StandardDetailPage.tsx` | modify | Disable purchase/upload buttons with reason; invalidate the standard query after upload/delete. |

---

### Task 1: ISO stage helper

**Files:**
- Create: `backend/app/core/iso_stages.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_draft_stage(stage_code: str | None) -> bool`

- [ ] **Step 1: Create the helper**

Create `backend/app/core/iso_stages.py`:

```python
"""
ISO lifecycle stage helpers.

ISO stage codes are "major.minor" strings (e.g. "30.00", "60.60"). The major
number tracks the lifecycle: 10-50 are pre-publication drafts, 60 is
publication, 90 is periodic review, 95 is withdrawal.

Kept dependency-free and in core/ rather than importing from
app/tasks/feeds.py, which holds the full stage tables but is a Celery task
module that services must not import.
"""

# First published stage. Anything below this has no purchasable document.
_FIRST_PUBLISHED_MAJOR = 60


def is_draft_stage(stage_code: str | None) -> bool:
    """
    True when the stage code is pre-publication (major < 60).

    An absent or unparseable stage code returns False — manually created
    standards carry no stage code and must not be silently locked out of
    upload and purchase.
    """
    if not stage_code:
        return False
    try:
        major = int(str(stage_code).split(".")[0])
    except (ValueError, IndexError):
        return False
    return major < _FIRST_PUBLISHED_MAJOR
```

- [ ] **Step 2: Run the assertion script and confirm every case passes**

Run:

```bash
docker compose exec -T web python -c "
from app.core.iso_stages import is_draft_stage as d
cases = [
    ('10.00', True), ('20.00', True), ('20.98', True), ('30.00', True),
    ('30.92', True), ('40.00', True), ('50.60', True),
    ('60.00', False), ('60.60', False), ('90.20', False), ('90.93', False),
    ('95.99', False),
    (None, False), ('', False), ('garbage', False), ('not.a.number', False),
]
for code, expected in cases:
    got = d(code)
    assert got == expected, f'{code!r}: expected {expected}, got {got}'
print('PASS', len(cases), 'cases')
"
```

Expected output: `PASS 16 cases`

- [ ] **Step 3: Cross-check the helper against real data**

This confirms the helper agrees with the 249/3,034 split the spec is based on.

Run:

```bash
docker compose exec -T web python -c "
import asyncio
from sqlalchemy import select
from app.database import async_session_factory
from app.models.standard import Standard
from app.core.iso_stages import is_draft_stage

async def main():
    async with async_session_factory() as s:
        rows = (await s.execute(select(Standard.stage_code))).all()
    drafts = sum(1 for (c,) in rows if is_draft_stage(c))
    print('drafts:', drafts, 'published:', len(rows) - drafts, 'total:', len(rows))
    assert drafts == 249, f'expected 249 drafts, got {drafts}'
    assert len(rows) == 3283, f'expected 3283 standards, got {len(rows)}'
    print('PASS')
asyncio.run(main())
" 2>&1 | grep -vE "INFO sqlalchemy|^\[|^SELECT|^FROM|^ *$"
```

Expected output includes: `drafts: 249 published: 3034 total: 3283` then `PASS`

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/iso_stages.py
git commit -m "Add ISO stage helper to identify pre-publication drafts"
```

---

### Task 2: Expose derived fields on the API

Schema fields and the service function that fills them must land together — adding required fields to `StandardDetail` without populating them breaks every response that builds it.

**Files:**
- Modify: `backend/app/schemas/standard.py` (`StandardDetail`, ends line 71)
- Modify: `backend/app/services/standard_service.py` (add function near `get_standard`, line 295)
- Modify: `backend/app/api/v1/standards.py` lines 130, 170-173, 239

**Interfaces:**
- Consumes: `is_draft_stage(stage_code: str | None) -> bool` from Task 1.
- Produces: `async get_purchasability(standard: Standard, db: AsyncSession) -> dict` returning keys `is_draft: bool`, `document_count: int`, `can_upload: bool`, `can_purchase: bool`, `purchase_blocked_reason: str | None`.

- [ ] **Step 1: Add the fields to the schema**

In `backend/app/schemas/standard.py`, inside `class StandardDetail`, add after `updated_at: datetime` and before `model_config`:

```python
    # ── Derived (computed by standard_service.get_purchasability) ─────────
    # Not ORM columns. Defaults exist so the model can still be built in
    # contexts that have no session, but every API path populates them
    # explicitly — see app/api/v1/standards.py.
    is_draft: bool = False
    document_count: int = 0
    can_upload: bool = True
    can_purchase: bool = False
    purchase_blocked_reason: str | None = None
```

- [ ] **Step 2: Add the service function**

In `backend/app/services/standard_service.py`, add these imports at the top of the file alongside the existing imports:

```python
from app.core.iso_stages import is_draft_stage
from app.models.document import Document
```

Then add this function immediately after `get_standard()` (which ends at line 300):

```python
DRAFT_BLOCKED_REASON = (
    "Not available — standard is still at draft stage ({stage}). "
    "Available once published."
)
NO_DOCUMENT_BLOCKED_REASON = (
    "Upload the standard document before marking it as purchased."
)


async def get_purchasability(standard: Standard, db: AsyncSession) -> dict:
    """
    Derive upload/purchase availability for a standard.

    Async and session-taking on purpose: document_count needs a COUNT query.
    These values must never become lazy ORM properties on Standard — a lazy
    load triggered from synchronous code (e.g. building a response model)
    raises MissingGreenlet under async SQLAlchemy.
    """
    draft = is_draft_stage(standard.stage_code)

    count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.standard_id == standard.id,
            Document.is_current == True,  # noqa: E712
        )
    )
    document_count: int = count_result.scalar_one()

    can_upload = not draft
    can_purchase = not draft and document_count > 0 and not standard.is_purchased

    reason: str | None = None
    if draft:
        stage = " ".join(
            p for p in (standard.stage_code, standard.stage_name) if p
        ) or "pre-publication"
        reason = DRAFT_BLOCKED_REASON.format(stage=stage)
    elif document_count == 0 and not standard.is_purchased:
        reason = NO_DOCUMENT_BLOCKED_REASON

    return {
        "is_draft": draft,
        "document_count": document_count,
        "can_upload": can_upload,
        "can_purchase": can_purchase,
        "purchase_blocked_reason": reason,
    }
```

`select` and `func` are already imported in this file; `AsyncSession` and `Standard` are too. Verify before adding duplicates.

- [ ] **Step 3: Populate the fields at all three construction sites**

In `backend/app/api/v1/standards.py`:

**Site A — `create_standard`, replace line 130:**

```python
    flags = await standard_service.get_purchasability(standard, db)
    return StandardDetail(
        **StandardDetail.model_validate(standard).model_dump(exclude=set(flags)),
        **flags,
    )
```

**Site B — `get_standard`, replace lines 170-173:**

```python
    flags = await standard_service.get_purchasability(standard, db)
    return StandardDetailWithAmendments(
        **StandardDetail.model_validate(standard).model_dump(exclude=set(flags)),
        **flags,
        amendments=[StandardListItem.model_validate(a) for a in amendments],
    )
```

**Site C — `purchase_standard`, replace line 239:**

```python
    flags = await standard_service.get_purchasability(standard, db)
    return StandardDetail(
        **StandardDetail.model_validate(standard).model_dump(exclude=set(flags)),
        **flags,
    )
```

`exclude=set(flags)` drops the five default-valued keys from the dump so the explicit `**flags` cannot collide with them — passing the same keyword twice is a `TypeError`.

- [ ] **Step 4: Restart and verify all three endpoints return the fields**

Run:

```bash
docker compose up --build -d web && sleep 6
T=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# a draft standard
D=$(docker exec -i ists_db psql -U ists -d ists -tAc \
  "SELECT id FROM standards WHERE split_part(stage_code,'.',1)::int < 60 LIMIT 1;" | tr -d ' ')
echo "--- draft ---"
curl -s "http://localhost:8000/api/v1/standards/$D" -H "Authorization: Bearer $T" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d[k] for k in ('stage_code','is_draft','document_count','can_upload','can_purchase','purchase_blocked_reason')})"

# a published standard that has a document and is not purchased
P=$(docker exec -i ists_db psql -U ists -d ists -tAc \
  "SELECT s.id FROM standards s JOIN documents dd ON dd.standard_id=s.id AND dd.is_current
   WHERE NOT s.is_purchased AND split_part(s.stage_code,'.',1)::int >= 60 LIMIT 1;" | tr -d ' ')
echo "--- published + has document ---"
curl -s "http://localhost:8000/api/v1/standards/$P" -H "Authorization: Bearer $T" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d[k] for k in ('stage_code','is_draft','document_count','can_upload','can_purchase','purchase_blocked_reason')})"
```

Expected: draft shows `is_draft: True, can_upload: False, can_purchase: False` and a reason naming its stage. Published-with-document shows `is_draft: False, document_count: 1, can_upload: True, can_purchase: True, purchase_blocked_reason: None`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/standard.py backend/app/services/standard_service.py backend/app/api/v1/standards.py
git commit -m "Expose draft and purchasability flags on standard detail responses"
```

---

### Task 3: Enforce the rules on the write paths

The flags from Task 2 are advisory until the server refuses the action.

**Files:**
- Modify: `backend/app/services/standard_service.py` (`purchase_standard`, line 348)
- Modify: `backend/app/api/v1/documents.py` (`upload_document`)

**Interfaces:**
- Consumes: `is_draft_stage()` (Task 1); `DRAFT_BLOCKED_REASON`, `NO_DOCUMENT_BLOCKED_REASON` (Task 2).
- Produces: `AppValidationError` (HTTP 422) from both write paths.

- [ ] **Step 1: Guard `purchase_standard`**

In `backend/app/services/standard_service.py`, in `purchase_standard`, immediately after the existing already-purchased early return (`return standard, False`) and before `old_snapshot = {...}`, insert:

```python
    # Order matters: the already-purchased no-op above stays first, so a
    # repeat call remains idempotent rather than turning into a 422.
    if is_draft_stage(standard.stage_code):
        stage = " ".join(
            p for p in (standard.stage_code, standard.stage_name) if p
        ) or "pre-publication"
        raise AppValidationError(DRAFT_BLOCKED_REASON.format(stage=stage))

    doc_count = await db.execute(
        select(func.count(Document.id)).where(
            Document.standard_id == standard.id,
            Document.is_current == True,  # noqa: E712
        )
    )
    if doc_count.scalar_one() == 0:
        raise AppValidationError(NO_DOCUMENT_BLOCKED_REASON)
```

Add `AppValidationError` to the existing `from app.core.exceptions import ...` line in this file.

- [ ] **Step 2: Guard the upload endpoint**

In `backend/app/api/v1/documents.py`, in `upload_document`, insert this as the **first** statement of the function body (after the docstring, before `max_bytes = ...`) so a draft is rejected before any bytes are read or written to storage:

```python
    # Reject drafts before touching the upload stream or storage.
    standard = await standard_service.get_standard(standard_id, db)
    if is_draft_stage(standard.stage_code):
        stage = " ".join(
            p for p in (standard.stage_code, standard.stage_name) if p
        ) or "pre-publication"
        raise AppValidationError(
            standard_service.DRAFT_BLOCKED_REASON.format(stage=stage)
        )
```

Add these imports to the top of `documents.py`:

```python
from app.core.exceptions import AppValidationError
from app.core.iso_stages import is_draft_stage
from app.services import standard_service
```

Check the existing import block first — `AppValidationError` and `standard_service` may already be imported. `get_standard` raises `NotFoundError` (404) for a missing standard, preserving the endpoint's documented 404 behaviour.

- [ ] **Step 3: Verify both guards reject with 422**

Run:

```bash
docker compose up --build -d web && sleep 6
T=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

D=$(docker exec -i ists_db psql -U ists -d ists -tAc \
  "SELECT id FROM standards WHERE split_part(stage_code,'.',1)::int < 60 LIMIT 1;" | tr -d ' ')
echo "--- purchase a draft (expect 422) ---"
curl -s -w "\nHTTP %{http_code}\n" -X POST "http://localhost:8000/api/v1/standards/$D/purchase" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{}'

echo "--- upload to a draft (expect 422) ---"
echo "dummy pdf" > /tmp/gate_test.pdf
curl -s -w "\nHTTP %{http_code}\n" -X POST "http://localhost:8000/api/v1/standards/$D/documents" \
  -H "Authorization: Bearer $T" -F "file=@/tmp/gate_test.pdf"

N=$(docker exec -i ists_db psql -U ists -d ists -tAc \
  "SELECT s.id FROM standards s WHERE NOT s.is_purchased
     AND split_part(s.stage_code,'.',1)::int >= 60
     AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.standard_id=s.id AND d.is_current) LIMIT 1;" | tr -d ' ')
echo "--- purchase a published standard with no document (expect 422) ---"
curl -s -w "\nHTTP %{http_code}\n" -X POST "http://localhost:8000/api/v1/standards/$N/purchase" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{}'

echo "--- re-purchase an already-purchased standard (expect 200, still idempotent) ---"
A=$(docker exec -i ists_db psql -U ists -d ists -tAc "SELECT id FROM standards WHERE is_purchased LIMIT 1;" | tr -d ' ')
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "http://localhost:8000/api/v1/standards/$A/purchase" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d '{}'
rm -f /tmp/gate_test.pdf
```

Expected: first three return `HTTP 422` with the matching reason in `detail`; the last returns `HTTP 200`.

- [ ] **Step 4: Confirm no draft was purchased and no document was stored**

Run:

```bash
docker exec -i ists_db psql -U ists -d ists -c "
SELECT count(*) AS drafts_purchased FROM standards
 WHERE is_purchased AND split_part(stage_code,'.',1)::int < 60;
SELECT count(*) AS docs_on_drafts FROM documents d
  JOIN standards s ON s.id=d.standard_id
 WHERE split_part(s.stage_code,'.',1)::int < 60;"
```

Expected: both counts `0`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/standard_service.py backend/app/api/v1/documents.py
git commit -m "Reject purchase and upload for draft-stage standards"
```

---

### Task 4: Gate the purchase button in the UI

**Files:**
- Modify: `frontend/src/api/standards.ts` (`Standard`, lines 10-25)
- Modify: `frontend/src/pages/StandardDetailPage.tsx` (lines 1109-1130)

**Interfaces:**
- Consumes: the five fields returned by `GET /standards/{id}` (Task 2).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the fields to the TypeScript type**

In `frontend/src/api/standards.ts`, inside `export interface Standard`, add after `created_at: string;`:

```typescript
  is_draft: boolean;
  document_count: number;
  can_upload: boolean;
  can_purchase: boolean;
  purchase_blocked_reason: string | null;
```

- [ ] **Step 2: Disable the button and show the reason**

In `frontend/src/pages/StandardDetailPage.tsx`, replace the `else` branch of the `standard.is_purchased` ternary (lines 1109-1130, the block beginning `(isAdmin || isManager) && (`) with:

```tsx
                  (isAdmin || isManager) && (
                    <div className="flex flex-col gap-1">
                      <Button
                        size="sm"
                        onClick={handlePurchase}
                        disabled={purchaseMutation.isPending || !standard.can_purchase}
                        title={standard.purchase_blocked_reason ?? undefined}
                        className="h-7 px-3 bg-teal-600 hover:bg-teal-700 text-xs gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {purchaseMutation.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          "Mark as Purchased"
                        )}
                      </Button>
                      {standard.purchase_blocked_reason && (
                        <p className="text-[11px] text-muted-foreground max-w-xs leading-snug">
                          {standard.purchase_blocked_reason}
                        </p>
                      )}
                    </div>
                  )
```

- [ ] **Step 3: Verify in the browser**

Run `docker compose up -d frontend`, open `http://localhost:5173`, log in as `admin@ists.local` / `Admin1234!`.

Get one URL of each kind to visit:

```bash
docker exec -i ists_db psql -U ists -d ists -c "
SELECT 'DRAFT      -> /standards/'||id FROM standards
 WHERE split_part(stage_code,'.',1)::int < 60 LIMIT 1;
SELECT 'NO DOC     -> /standards/'||s.id FROM standards s
 WHERE NOT s.is_purchased AND split_part(s.stage_code,'.',1)::int >= 60
   AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.standard_id=s.id AND d.is_current) LIMIT 1;
SELECT 'HAS DOC    -> /standards/'||s.id FROM standards s
 JOIN documents d ON d.standard_id=s.id AND d.is_current
 WHERE NOT s.is_purchased AND split_part(s.stage_code,'.',1)::int >= 60 LIMIT 1;"
```

Expected: draft → button greyed, reason names the stage. No-doc → button greyed, reason asks for a document. Has-doc → button enabled, no reason text.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/standards.ts frontend/src/pages/StandardDetailPage.tsx
git commit -m "Disable purchase button with reason when unavailable"
```

---

### Task 5: Gate upload and re-enable purchase after a successful upload

This task delivers the "purchase becomes available after upload" behaviour. Without the cache invalidation the button stays greyed until a manual refresh.

**Files:**
- Modify: `frontend/src/pages/StandardDetailPage.tsx` — `DocumentsTabProps` (line 734), `DocumentsTab` signature (line 738), delete mutation (line 750), upload button (line 797), `UploadModal` `onSuccess` (line 995), render site (line 1293)

**Interfaces:**
- Consumes: `can_upload` from the `Standard` type (Task 4).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Accept the new props**

In `interface DocumentsTabProps` (line 734), add alongside `standardId: string;`:

```typescript
  canUpload: boolean;
  blockedReason: string | null;
```

Change the component signature (line 738) to:

```tsx
function DocumentsTab({ standardId, canUpload: stageAllowsUpload, blockedReason }: DocumentsTabProps) {
```

The existing local `const canUpload = isAdmin || isManager;` (line 780) stays as the role check. Renaming the incoming prop to `stageAllowsUpload` avoids shadowing it — both checks are required.

- [ ] **Step 2: Apply the stage check to the upload button**

Replace the upload button block (lines 796-808) with:

```tsx
      {canUpload && (
        <div className="flex flex-col items-end gap-1">
          <Button
            size="sm"
            onClick={() => setShowUploadModal(true)}
            disabled={!stageAllowsUpload}
            title={!stageAllowsUpload ? (blockedReason ?? undefined) : undefined}
            className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload Document
          </Button>
          {!stageAllowsUpload && blockedReason && (
            <p className="text-[11px] text-muted-foreground max-w-xs text-right leading-snug">
              {blockedReason}
            </p>
          )}
        </div>
      )}
```

- [ ] **Step 3: Invalidate the standard query after upload and delete**

The purchase button reads `can_purchase` from the `["standard", id]` query, so that query — not just `["documents", …]` — must be refetched whenever the document set changes.

Replace the `UploadModal` `onSuccess` (lines 993-995) with:

```tsx
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
            // can_purchase lives on the standard query; without this the
            // purchase button stays disabled until a manual refresh.
            queryClient.invalidateQueries({ queryKey: ["standard", standardId] });
          }}
```

And in the delete mutation `onSuccess` (line 750), add the same second invalidation so removing the last document re-disables purchase:

```tsx
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
      queryClient.invalidateQueries({ queryKey: ["standard", standardId] });
      setDeletingId(null);
    },
```

- [ ] **Step 4: Pass the props at the render site**

Replace line 1293:

```tsx
              <DocumentsTab
                standardId={id!}
                canUpload={standard.can_upload}
                blockedReason={standard.purchase_blocked_reason}
              />
```

- [ ] **Step 5: Verify the live enablement end to end**

In the browser, open a **published standard with no document** (query from Task 4, Step 3). Confirm: upload button enabled, purchase button greyed with "Upload the standard document…".

Upload any small PDF. Confirm **without refreshing the page** that the purchase button becomes enabled and the reason text disappears. Then click it and confirm the standard shows `✓ Purchased`.

Then open a **draft** standard and confirm the upload button is greyed with the stage reason.

Confirm the DB agrees:

```bash
docker exec -i ists_db psql -U ists -d ists -c "
SELECT s.iso_reference, s.stage_code, s.is_purchased,
       (SELECT count(*) FROM documents d WHERE d.standard_id=s.id AND d.is_current) AS docs
FROM standards s WHERE s.is_purchased ORDER BY s.purchased_at DESC NULLS LAST LIMIT 3;"
```

Expected: the newly purchased standard appears with `docs >= 1` and a published `stage_code`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/StandardDetailPage.tsx
git commit -m "Gate upload by stage and refresh purchasability after upload"
```

---

### Task 6: Full-matrix verification and cleanup

**Files:** none modified — verification only.

- [ ] **Step 1: Confirm every spec case in one pass**

Run:

```bash
T=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

check () {
  local label="$1" sql="$2" exp_upload="$3" exp_purchase="$4"
  local sid
  sid=$(docker exec -i ists_db psql -U ists -d ists -tAc "$sql" | tr -d ' ')
  if [ -z "$sid" ]; then echo "SKIP  $label (no matching row)"; return; fi
  curl -s "http://localhost:8000/api/v1/standards/$sid" -H "Authorization: Bearer $T" \
   | python3 -c "
import sys,json
d=json.load(sys.stdin)
ok = str(d['can_upload'])=='$exp_upload' and str(d['can_purchase'])=='$exp_purchase'
print(('PASS  ' if ok else 'FAIL  ')+'$label',
      '| can_upload=%s can_purchase=%s docs=%s' % (d['can_upload'], d['can_purchase'], d['document_count']))
"
}

check "draft"                  "SELECT id FROM standards WHERE split_part(stage_code,'.',1)::int < 60 LIMIT 1;" False False
check "published, no document" "SELECT s.id FROM standards s WHERE NOT s.is_purchased AND split_part(s.stage_code,'.',1)::int >= 60 AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.standard_id=s.id AND d.is_current) LIMIT 1;" True False
check "published, has document" "SELECT s.id FROM standards s JOIN documents d ON d.standard_id=s.id AND d.is_current WHERE NOT s.is_purchased AND split_part(s.stage_code,'.',1)::int >= 60 LIMIT 1;" True True
check "already purchased"      "SELECT id FROM standards WHERE is_purchased LIMIT 1;" True False
```

Expected: four `PASS` lines (the last may print `SKIP` only if no purchased standard exists).

- [ ] **Step 2: Confirm the feed pipeline is untouched**

This change must not affect polling. Run:

```bash
docker exec -i ists_db psql -U ists -d ists -c "
SELECT k.label, count(f.id) AS feeds,
       count(*) FILTER (WHERE f.last_poll_status='ok') AS ok
FROM api_keys k LEFT JOIN rss_feeds f ON f.api_key_id=k.id
GROUP BY k.label ORDER BY k.label;"
```

Expected: unchanged from before this work — key-1 25/25, key-2 16/16, key-3 16/16.

- [ ] **Step 3: Drop the diagnostic tables left over from the feed investigation**

```bash
docker exec -i ists_db psql -U ists -d ists -c "DROP TABLE IF EXISTS _prod_baseline; DROP TABLE IF EXISTS _sweep;"
```

These were created during the RSS key investigation and are not part of the schema; leaving them would pollute future dumps.

- [ ] **Step 4: Final commit if anything is outstanding**

```bash
git status --short
```

Expected: clean. If not, review and commit deliberately.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `is_draft_stage()` in `core/iso_stages.py`, fail-open on missing code | 1 |
| Stage rule = major < 60, verified as 249 drafts | 1 |
| Five derived fields on `StandardDetail` | 2 |
| `get_purchasability()` async, own COUNT, never an ORM property | 2 |
| `document_count` counts `is_current = True` only | 2 |
| All three `StandardDetail` sites populated (130, 171, 239) | 2 |
| Guard `purchase_standard` for draft and no-document | 3 |
| Already-purchased stays an idempotent no-op, not a 422 | 3 |
| Guard upload for draft, before reading the file | 3 |
| `AppValidationError` → 422, no new error plumbing | 3 |
| Frontend `Standard` type gains the fields | 4 |
| Purchase button visible-but-disabled with reason | 4 |
| Upload button gated by stage plus role | 5 |
| Invalidate `["standard", id]` on upload **and** delete | 5 |
| Verification matrix over all four cases | 6 |
| Withdrawn (stage 95) remains purchasable | covered by the rule; asserted in 1 Step 3 (3,034 published includes 1,376 withdrawn) |
| No migration, no feed changes | 6 Step 2 asserts feeds untouched |

No gaps.

**Placeholder scan:** No TBD/TODO. Every code step contains complete code; every verification step contains a runnable command and its expected output.

**Type consistency:** `is_draft_stage(stage_code: str | None) -> bool` is defined in Task 1 and used identically in Tasks 2 and 3. `get_purchasability(standard, db) -> dict` is defined in Task 2 and its five keys are consumed by name in Tasks 2, 4, 5 and 6. The prop rename (`canUpload` → local alias `stageAllowsUpload`) is introduced in Task 5 Step 1 and used consistently in Steps 2 and 4. `DRAFT_BLOCKED_REASON` / `NO_DOCUMENT_BLOCKED_REASON` are defined in Task 2 and referenced in Task 3.
