# Manual Standard Entry & Standards Body Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let managers/admins manually add a standard (for bodies like ASTM with no RSS feed), and add a `standards_body` field (ISO/IEC/IEEE/ASTM/Other) populated for both manually-created and feed-discovered standards, filterable in the Standards Library.

**Architecture:** A new nullable `standards_body` string column on `standards`, populated by the existing feed parser (derived from the org prefix it already extracts) and by a new manual-creation form. Creation is a new `POST /api/v1/standards` endpoint that writes the same `StandardHistory`/audit-log/notification trail as every other mutation in this codebase, gated to manager+admin.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, React + TypeScript + TanStack Query. No new dependencies.

## Global Constraints

- **No pytest suite exists in this repo.** Verification for every task is live: `docker compose exec` + `curl` + `psql`, and `npx tsc --noEmit` for frontend — this repo's established practice throughout its history, not an oversight to fix here.
- **Enums**: this codebase creates every Postgres enum via `op.execute("CREATE TYPE x_enum AS ENUM (...)")` + `create_type=False`. `standards_body` is deliberately NOT a Postgres enum — it's a plain `VARCHAR(50)`, because the frontend's "Other" option must accept arbitrary free text, which a fixed enum would reject.
- **No ORM `relationship()` anywhere in this codebase.** Plain FK columns and explicit `select()`/`join()` only.
- **Migration numbering**: current head is `0011_add_document_tags.py`. The new migration is `0012`.
- **Local imports for circular-import avoidance**: `standard_service.py`'s existing `purchase_standard()` imports `EventType`, `EventSource`, `StandardHistory`, and `write_audit_log` *inside* the function body, not at module top level. Match this exact style for the new `create_standard_manually()` — it's not a style preference, it avoids a real circular import in this codebase's module graph.
- **Commit-then-dispatch ordering**: `purchase_standard`'s API route calls `await db.commit()` *before* dispatching `send_bulk_notification.delay(...)`. The new create-standard route follows the same ordering — notifications only fire once the row is durably persisted.

---

### Task 1: `standards_body` migration and model

**Files:**
- Create: `backend/alembic/versions/0012_add_standards_body.py`
- Modify: `backend/app/models/standard.py`

**Interfaces:**
- Produces: `Standard.standards_body: str | None` column — used by every later task.

- [ ] **Step 1: Write the migration**

```python
"""Add standards_body to standards (ISO/IEC/IEEE/ASTM/Other).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('standards', sa.Column(
        'standards_body', sa.String(50), nullable=True,
        comment="Issuing body (ISO, IEC, IEEE, ASTM, or free text via 'Other') — "
                "populated for both feed-sourced and manually-created standards."
    ))
    op.create_index('ix_standards_standards_body', 'standards', ['standards_body'])


def downgrade() -> None:
    op.drop_index('ix_standards_standards_body', table_name='standards')
    op.drop_column('standards', 'standards_body')
```

This is deliberately NOT a Postgres enum (no `CREATE TYPE`) — see Global Constraints.

- [ ] **Step 2: Add the column to the model**

In `backend/app/models/standard.py`, add the import `String` if not already present (it already is, via the existing `String(100)` on `iso_reference`), and add this field. Insert it right after the existing `tc_committee` field:

```python
    tc_committee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    standards_body: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
```

Also update the model's docstring schema comment block at the top of the file to add:
```
  standards_body  VARCHAR(50) NULLABLE  (ISO, IEC, IEEE, ASTM, or free text)
```

- [ ] **Step 3: Verify — apply the migration against the live stack**

```bash
docker compose up -d db redis web worker beat mailhog
docker compose exec -T web alembic upgrade head
docker compose exec -T web alembic current
```
Expected: last line prints `0012 (head)`.

```bash
docker compose exec -T db psql -U ists -d ists -c "\d standards" | grep standards_body
```
Expected: shows `standards_body | character varying(50) |` with an index listed further down in the `\d` output (`ix_standards_standards_body`).

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0012_add_standards_body.py backend/app/models/standard.py
git commit -m "feat: add standards_body column to standards"
```

---

### Task 2: Feed ingestion derives `standards_body`, plus backfill script

**Files:**
- Modify: `backend/app/tasks/feeds.py`
- Create: `backend/scripts/backfill_standards_body.py`

**Interfaces:**
- Consumes: `Standard.standards_body` (Task 1).
- Produces: `parse_iso_entry()`'s returned dict gains a `"standards_body"` key — consumed by `_process_entry()` in this same task.

- [ ] **Step 1: Derive `standards_body` in `parse_iso_entry()`**

In `backend/app/tasks/feeds.py`, find this existing block (around line 257):

```python
    org_part = match.group(1).strip()
    num_part = match.group(2).strip()
    iso_reference = f"{org_part} {num_part}".upper()
```

`org_part` is already the full org+qualifier chain the regex matched — e.g. `"ISO"`, `"ISO/WD"`, `"IEC/TS"`, `"ISO/IEC/IEEE"`. Leave this block unchanged, but in the function's final `return { ... }` dict (around line 324), add one new key:

```python
    return {
        "iso_reference": iso_reference,
        "title": title,
        "edition": edition,
        "stage": stage,
        "stage_name": stage_name,
        "status": status,
        "tc_committee": tc_committee,
        "standards_body": org_part.split("/")[0].strip(),
        "published_date": published_date,
        "external_url": link or None,
        "event_type_hint": event_type_hint,
    }
```

`org_part.split("/")[0]` takes the leading org token — `"ISO/WD"` → `"ISO"`, `"IEC/TS"` → `"IEC"`, `"ISO/IEC/IEEE"` → `"ISO"` — matching the exact vocabulary (ISO/IEC/IEEE) the frontend's fixed dropdown will offer in Task 6.

- [ ] **Step 2: Set it on both the create and update paths in `_process_entry()`**

In the new-standard branch (around line 395), add `standards_body` to the `Standard(...)` constructor call, right after `tc_committee`:

```python
        standard = Standard(
            iso_reference=iso_ref,
            title=parsed["title"],
            edition=parsed["edition"],
            tc_committee=tc_committee,
            standards_body=parsed["standards_body"],
            status=new_status,
            source_feed_id=feed.id,
            external_url=parsed["external_url"],
            content_hash=content_hash,
            stage_code=parsed["stage"],
            stage_name=parsed["stage_name"],
            published_date=parsed["published_date"],
            base_reference=_extract_base_reference(iso_ref),
        )
```

In the update branch (around line 479), add one line right after `standard.tc_committee = tc_committee`:

```python
    standard.title = parsed["title"]
    standard.edition = parsed["edition"] or standard.edition
    standard.status = new_status
    standard.tc_committee = tc_committee
    standard.standards_body = parsed["standards_body"]
    standard.content_hash = content_hash
```

- [ ] **Step 3: Write the backfill script**

```python
"""
One-time backfill: populate standards_body for standards created before this field existed.

Run after applying migration 0012:
  docker compose exec web python scripts/backfill_standards_body.py
"""
import asyncio
import sys

import structlog
from sqlalchemy import select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.standard import Standard
from app.tasks.feeds import _REFERENCE_RE

setup_logging()
log = structlog.get_logger(__name__)


def _derive_standards_body(iso_reference: str) -> str | None:
    """Same extraction _process_entry() applies to newly-parsed feed entries."""
    match = _REFERENCE_RE.match(iso_reference)
    if not match:
        return None
    return match.group(1).split("/")[0].strip()


async def backfill() -> None:
    log.info("backfill_standards_body_starting")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Standard).where(Standard.standards_body.is_(None))
        )
        standards = result.scalars().all()

        updated = 0
        for s in standards:
            body = _derive_standards_body(s.iso_reference)
            if body:
                s.standards_body = body
                updated += 1

        await session.commit()
        print(f"Backfilled {updated} of {len(standards)} standards without a standards_body")


if __name__ == "__main__":
    asyncio.run(backfill())
```

- [ ] **Step 4: Verify — run the backfill against the live DB, then confirm new feed entries also get tagged**

```bash
docker compose exec -T web python scripts/backfill_standards_body.py
docker compose exec -T db psql -U ists -d ists -c "SELECT standards_body, COUNT(*) FROM standards GROUP BY standards_body ORDER BY 2 DESC;"
```
Expected: a breakdown showing `ISO`, `IEC`, and/or `IEEE` counts (matching whatever org prefixes exist in the seeded/live data), with `NULL` only for rows whose `iso_reference` didn't match the pattern (should be none, since manual entry doesn't exist until Task 3).

```bash
docker compose restart web worker
```

Confirm the code compiles and imports correctly:
```bash
docker compose exec -T web python -c "import app.tasks.feeds; print('OK')"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/feeds.py backend/scripts/backfill_standards_body.py
git commit -m "feat: derive standards_body from feed entries, backfill existing rows"
```

---

### Task 3: Manual standard creation — schema, service, endpoint

**Files:**
- Modify: `backend/app/schemas/standard.py`
- Modify: `backend/app/services/standard_service.py`
- Modify: `backend/app/api/v1/standards.py`

**Interfaces:**
- Consumes: `Standard.standards_body` (Task 1).
- Produces: `StandardCreate` schema; `standard_service.create_standard_manually(payload, actor_id, db) -> Standard`; `POST /api/v1/standards` endpoint — the core deliverable of this feature.

- [ ] **Step 1: Add `StandardCreate` and `standards_body` fields to `backend/app/schemas/standard.py`**

Add `standards_body: str | None = None` to both `StandardListItem` and `StandardDetail` (it flows through automatically to `StandardGrouped`/`StandardDetailWithAmendments`, which subclass them):

```python
class StandardListItem(BaseModel):
    """Lightweight projection used in the standards list table."""

    id: uuid.UUID
    iso_reference: str
    title: str
    edition: str | None
    tc_committee: str | None
    standards_body: str | None = None
    status: StandardStatus
    is_purchased: bool
    stage_code: str | None = None
    stage_name: str | None = None
    published_date: date | None = None
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class StandardDetail(BaseModel):
    """Full standard record returned on the detail page."""

    id: uuid.UUID
    iso_reference: str
    title: str
    edition: str | None
    tc_committee: str | None
    standards_body: str | None = None
    status: StandardStatus
    is_purchased: bool
    purchased_at: datetime | None
    purchase_notes: str | None
    external_url: str | None
    source_feed_id: uuid.UUID | None
    stage_code: str | None = None
    stage_name: str | None = None
    published_date: date | None = None
    parent_standard_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

Add the new creation schema anywhere in the file (e.g. right after the imports, before `StandardListItem`):

```python
class StandardCreate(BaseModel):
    """Payload for manually adding a standard (manager+), not via RSS discovery."""

    iso_reference: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1)
    standards_body: str = Field(..., min_length=1, max_length=50)
    edition: str | None = Field(default=None, max_length=50)
    tc_committee: str | None = Field(default=None, max_length=100)
    status: StandardStatus = StandardStatus.active
    published_date: date | None = None
    external_url: str | None = None
```

This requires adding `Field` to the existing `from pydantic import BaseModel, ConfigDict` import line:

```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 2: Add `create_standard_manually()` to `backend/app/services/standard_service.py`**

Add this function anywhere after `purchase_standard()` (or before it — placement doesn't matter, but keep it near the other write operation for discoverability):

```python
async def create_standard_manually(
    payload: "StandardCreate",
    actor_id: uuid.UUID,
    db: AsyncSession,
) -> Standard:
    """
    Create a standard by hand (admin/manager data entry), not via RSS discovery.

    Used for standards bodies (ASTM, etc.) that don't publish an RSS feed.
    Raises ConflictError if a standard with this iso_reference already exists.
    """
    # Local imports, matching purchase_standard()'s existing style in this same
    # file (avoids a module-level circular import between standard_service and
    # standard_history/audit_service/the feeds task module).
    from app.models.standard_history import EventSource, EventType, StandardHistory
    from app.services.audit_service import write_audit_log
    from app.tasks.feeds import _extract_base_reference

    existing = await db.execute(
        select(Standard).where(Standard.iso_reference == payload.iso_reference)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            f"A standard with reference '{payload.iso_reference}' already exists."
        )

    standard = Standard(
        iso_reference=payload.iso_reference,
        title=payload.title,
        standards_body=payload.standards_body,
        edition=payload.edition,
        tc_committee=payload.tc_committee,
        status=payload.status,
        published_date=payload.published_date,
        external_url=payload.external_url,
        base_reference=_extract_base_reference(payload.iso_reference),
        # source_feed_id and content_hash stay NULL — this standard has no feed origin
    )
    db.add(standard)
    await db.flush()

    history = StandardHistory(
        standard_id=standard.id,
        event_type=EventType.new,
        old_value=None,
        new_value={
            "iso_reference": standard.iso_reference,
            "title": standard.title,
            "standards_body": standard.standards_body,
            "edition": standard.edition,
            "tc_committee": standard.tc_committee,
            "status": standard.status.value,
            "published_date": str(standard.published_date) if standard.published_date else None,
        },
        source=EventSource.manual,
        triggered_by=actor_id,
        notes="Standard added manually",
    )
    db.add(history)

    await write_audit_log(
        db,
        action="standard.created",
        resource_type="standard",
        actor_id=actor_id,
        resource_id=standard.id,
        payload={"iso_reference": standard.iso_reference, "standards_body": standard.standards_body},
    )

    log.info("standard_created_manually", standard_id=str(standard.id), actor_id=str(actor_id))
    return standard
```

Add `ConflictError` to the existing `from app.core.exceptions import NotFoundError` import:

```python
from app.core.exceptions import ConflictError, NotFoundError
```

Add `StandardCreate` to the existing `from app.schemas.standard import (...)` import (or, if using the string-quoted type hint `"StandardCreate"` shown above to sidestep any import-order concern, add the real import anyway since it's needed at runtime for `payload.iso_reference` attribute access — Python doesn't need the string-quoted forward reference to actually import it, but it's cleaner and avoids confusion to just import it directly):

```python
from app.schemas.standard import StandardCreate, StandardGrouped, StandardListItem, StandardVersion
```

(and remove the string quotes around `"StandardCreate"` in the function signature — write it as a normal unquoted type hint: `payload: StandardCreate`.)

- [ ] **Step 3: Add the endpoint to `backend/app/api/v1/standards.py`**

This file's current top-level import is `from fastapi import APIRouter, Query` — no `status`, since no existing route in it sets an explicit `status_code`. Change it to:

```python
from fastapi import APIRouter, Query, status
```

Add `StandardCreate` to the existing `from app.schemas.standard import (...)` import block:

```python
from app.schemas.standard import (
    StandardCreate,
    StandardDetail,
    StandardDetailWithAmendments,
    StandardGrouped,
    StandardHistoryItem,
    StandardListItem,
)
```

Add the new route. Place it right after the `list_standards` route and before the `/committees` route (order among GET routes doesn't matter for correctness here since this is a POST on a distinct path pattern, but grouping create-next-to-list keeps the file readable):

```python
@router.post(
    "",
    response_model=StandardDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a standard (manager+)",
)
async def create_standard(
    payload: StandardCreate,
    db: DBSession,
    current_user: ManagerOrAdminUser,
) -> StandardDetail:
    """
    Add a standard by hand — for standards bodies (ASTM, etc.) with no RSS feed.
    Returns 409 if a standard with this reference already exists.
    """
    standard = await standard_service.create_standard_manually(payload, current_user.id, db)
    await db.commit()

    from app.tasks.notifications import send_bulk_notification
    send_bulk_notification.delay({
        "event_type": "new",
        "standard_id": str(standard.id),
        "triggered_by_id": str(current_user.id),
    })

    return StandardDetail.model_validate(standard)
```

Note: `ManagerOrAdminUser` is already imported further down in this file (`from app.api.deps import ManagerOrAdminUser`, used by the existing `purchase_standard` route) — if that import line appears after this new route in the file, Python doesn't care about import statement ordering within a module as long as it's imported somewhere at module level before the route function is *called* (not before it's *defined*), so no reordering is required. If you'd like the file tidier, you can move that import up to the main import block near the top instead — either way works.

- [ ] **Step 4: Verify — full live round trip**

```bash
docker compose restart web
until curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs | grep -q 200; do sleep 1; done

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")

echo "--- create a manual ASTM standard ---"
RESP=$(curl -s -w "\nHTTP:%{http_code}\n" -X POST http://localhost:8000/api/v1/standards -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "iso_reference": "ASTM D638-14",
  "title": "Standard Test Method for Tensile Properties of Plastics",
  "standards_body": "ASTM",
  "edition": "2014",
  "external_url": "https://www.astm.org/d0638-14.html"
}')
echo "$RESP"
STD_ID=$(echo "$RESP" | head -1 | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "--- duplicate reference should 409 ---"
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/standards -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "iso_reference": "ASTM D638-14",
  "title": "Duplicate attempt",
  "standards_body": "ASTM"
}'

echo "--- history row recorded as manual ---"
curl -s "http://localhost:8000/api/v1/standards/$STD_ID/history" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print([(h['event_type'], h['source']) for h in d['items']])"

echo "--- audit log entry ---"
curl -s "http://localhost:8000/api/v1/admin/audit-logs?action=standard.created&page_size=1" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['payload'] if d['items'] else 'MISSING')"
```

Expected: create returns `201` with `standards_body: "ASTM"` in the body; duplicate returns `409`; history shows `("new", "manual")`; audit log shows `{"iso_reference": "ASTM D638-14", "standards_body": "ASTM"}`.

Clean up the test standard:
```bash
docker compose exec -T db psql -U ists -d ists -c "DELETE FROM standards WHERE id='$STD_ID';"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/standard.py backend/app/services/standard_service.py backend/app/api/v1/standards.py
git commit -m "feat: add manual standard creation endpoint"
```

---

### Task 4: Standards Body filtering and distinct-values endpoint

**Files:**
- Modify: `backend/app/services/standard_service.py`
- Modify: `backend/app/api/v1/standards.py`

**Interfaces:**
- Consumes: `Standard.standards_body` (Task 1).
- Produces: `standard_service.list_standards_bodies(db) -> list[str]`; `standards_body` filter param on `list_standards()`/`get_grouped_standards()`; `GET /api/v1/standards/standards-bodies` endpoint — used by the frontend (Task 5).

- [ ] **Step 1: Add the filter to `list_standards()` and `get_grouped_standards()`**

In `backend/app/services/standard_service.py`, add `standards_body: str | None = None` to `list_standards()`'s parameter list (right after `tc_committee`), and add this condition right after the existing `tc_committee` condition:

```python
    if tc_committee is not None:
        conditions.append(Standard.tc_committee == tc_committee)
    if standards_body is not None:
        conditions.append(Standard.standards_body == standards_body)
```

Update the docstring's `Args:` block to add:
```
        standards_body: Exact match on standards_body field.
```

Add the same parameter to `_matches_filters()`'s signature (right after `tc_committee`) and check (right after the `tc_committee` check):

```python
def _matches_filters(
    standard: Standard,
    *,
    search: str | None,
    status: StandardStatus | None,
    tc_committee: str | None,
    standards_body: str | None,
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
    if standards_body is not None and standard.standards_body != standards_body:
        return False
    if not _stage_matches(standard.stage_code, stage):
        return False
    if is_purchased is not None and standard.is_purchased != is_purchased:
        return False
    return True
```

Add `standards_body: str | None = None` to `get_grouped_standards()`'s parameter list (right after `tc_committee`), and pass it through at its `_matches_filters(...)` call site (right after the existing `tc_committee=tc_committee,` line):

```python
        if not _matches_filters(
            primary,
            search=search,
            status=status,
            tc_committee=tc_committee,
            standards_body=standards_body,
            stage=stage,
            is_purchased=is_purchased,
            tag_matched_ids=tag_matched_ids,
        ):
```

- [ ] **Step 2: Add `list_standards_bodies()`**

Add this function right after the existing `list_committees()`:

```python
async def list_standards_bodies(db: AsyncSession) -> list[str]:
    """Return the distinct set of standards_body values across all standards, for filter dropdowns."""
    result = await db.execute(
        select(Standard.standards_body)
        .where(Standard.standards_body.is_not(None))
        .distinct()
        .order_by(Standard.standards_body.asc())
    )
    return [row[0] for row in result.all()]
```

- [ ] **Step 3: Wire the filter and new endpoint into `backend/app/api/v1/standards.py`**

Add `standards_body: str | None = Query(default=None)` to `list_standards()`'s route parameters (right after `tc_committee`), and thread it through to both `standard_service.get_grouped_standards(...)` and `standard_service.list_standards(...)` calls (right after their existing `tc_committee=tc_committee,` lines).

Add the new route right after the existing `/committees` route:

```python
@router.get(
    "/standards-bodies",
    response_model=list[str],
    summary="List distinct standards bodies across all standards, for filter dropdowns (viewer+)",
)
async def list_standards_bodies(
    db: DBSession,
    _: CurrentUser,
) -> list[str]:
    return await standard_service.list_standards_bodies(db)
```

- [ ] **Step 4: Verify — filter and distinct-values endpoint live**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")

echo "--- distinct bodies ---"
curl -s "http://localhost:8000/api/v1/standards/standards-bodies" -H "Authorization: Bearer $TOKEN"
echo

echo "--- filter by body (flat) ---"
curl -s "http://localhost:8000/api/v1/standards?standards_body=ISO&grouped=false&page_size=3" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('total:', d['total'], [i['standards_body'] for i in d['items']])"

echo "--- filter by body (grouped) ---"
curl -s "http://localhost:8000/api/v1/standards?standards_body=ISO&grouped=true&page_size=3" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('total:', d['total'], [i['standards_body'] for i in d['items']])"
```

Expected: the distinct-bodies list includes `"ISO"` (and `"IEC"`/`"IEEE"` if present in seed data); both filtered queries return only `standards_body: "ISO"` items, with `total` strictly less than the unfiltered total.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/standard_service.py backend/app/api/v1/standards.py
git commit -m "feat: add standards_body filtering and distinct-values endpoint"
```

---

### Task 5: Frontend API client

**Files:**
- Modify: `frontend/src/api/standards.ts`

**Interfaces:**
- Produces: `standards_body` field on `Standard`/`StandardDetail`/`StandardGrouped`; `standards_body` on `StandardsListParams`; `createStandard()`; `listStandardsBodies()` — used by Tasks 6, 7.

- [ ] **Step 1: Add `standards_body` to the existing interfaces**

```typescript
export interface Standard {
  id: string;
  iso_reference: string;
  title: string;
  edition: string | null;
  tc_committee: string | null;
  standards_body: string | null;
  status: string;
  stage_code: string | null;
  stage_name: string | null;
  published_date: string | null;
  is_purchased: boolean;
  parent_standard_id: string | null;
  updated_at: string;
  created_at: string;
}
```

(`StandardDetail` and `StandardGrouped` both `extends Standard`, so they inherit this field automatically — no separate edit needed for them.)

Add `standards_body?: string` to `StandardsListParams`:

```typescript
export interface StandardsListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  tc_committee?: string;
  standards_body?: string;
  stage?: string;
  is_purchased?: boolean;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  grouped?: boolean;
}
```

- [ ] **Step 2: Add `createStandard()` and `listStandardsBodies()`**

Add a new `StandardCreatePayload` interface and the two functions, right after `listCommittees()`:

```typescript
export interface StandardCreatePayload {
  iso_reference: string;
  title: string;
  standards_body: string;
  edition?: string;
  tc_committee?: string;
  status?: string;
  published_date?: string;
  external_url?: string;
}

export async function listStandardsBodies(): Promise<string[]> {
  const { data } = await api.get<string[]>("/api/v1/standards/standards-bodies");
  return data;
}

export async function createStandard(payload: StandardCreatePayload): Promise<StandardDetail> {
  const { data } = await api.post<StandardDetail>("/api/v1/standards", payload);
  return data;
}
```

- [ ] **Step 3: Verify — typecheck**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: no errors. (No existing code constructs a `Standard`/`StandardDetail` object literal by hand — these are only ever received from API responses — so adding a required `standards_body` field doesn't break any existing call site.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/standards.ts
git commit -m "feat: add frontend API client for manual standard creation and standards body"
```

---

### Task 6: "Add Standard" modal

**Files:**
- Modify: `frontend/src/pages/StandardsPage.tsx`

**Interfaces:**
- Consumes: `createStandard`, `StandardCreatePayload` (Task 5); `useAuth()` (existing, for `isAdmin`/`isManager`); `Dialog`/`DialogContent`/`DialogHeader`/`DialogTitle`/`DialogDescription`/`DialogFooter` from `@/components/ui/dialog` (existing, used by `FeedsPage.tsx`'s "Add Feed" modal — same pattern reused here); `Label` from `@/components/ui/label` (existing).

- [ ] **Step 1: Add imports**

Add to the existing imports at the top of `StandardsPage.tsx`:

```typescript
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronRight, ChevronUp, Loader2, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import {
  createStandard, listCommittees, listStandards, type StandardCreatePayload,
  type StandardGrouped, type StandardsListParams,
} from "@/api/standards";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate } from "@/lib/utils";
```

(This replaces the existing `import { useState } from "react";`, the `lucide-react` import line, the `@/api/standards` import line, and adds three new imports — `Label`, `Dialog`-family, `useAuth` — plus `useMutation`/`useQueryClient` alongside the existing `useQuery` import, and `useNavigate` which is already imported.)

- [ ] **Step 2: Add the Standards Body dropdown options and form state**

Add near the other option constants at the top of the file (after `SORT_OPTIONS`):

```typescript
const STANDARDS_BODY_OPTIONS = ["ISO", "IEC", "IEEE", "ASTM", "Other"];

const DEFAULT_CREATE_FORM: StandardCreatePayload = {
  iso_reference: "",
  title: "",
  standards_body: "ISO",
  edition: "",
  tc_committee: "",
  status: "active",
  published_date: "",
  external_url: "",
};
```

Inside the `StandardsPage` component, add this state and mutation right after the existing `expandedGroups` state:

```tsx
  const { isAdmin, isManager } = useAuth();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<StandardCreatePayload>(DEFAULT_CREATE_FORM);
  const [otherBody, setOtherBody] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createStandard,
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["standards", "list"] });
      setShowCreate(false);
      setCreateForm(DEFAULT_CREATE_FORM);
      setOtherBody("");
      setCreateError(null);
      navigate(`/standards/${created.id}`);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setCreateError(err?.response?.data?.detail ?? "Failed to create standard");
    },
  });

  const canCreate = isAdmin || isManager;
```

- [ ] **Step 3: Add the "Add Standard" button to the header**

Replace the existing header block:

```tsx
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-indigo-400" />
            Standards Library
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total.toLocaleString()} standards` : "Loading…"}
          </p>
        </div>
      </div>
```

with:

```tsx
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-indigo-400" />
            Standards Library
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total.toLocaleString()} standards` : "Loading…"}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setShowCreate(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            Add Standard
          </Button>
        )}
      </div>
```

- [ ] **Step 4: Add the modal**

Add this right before the closing `</div>` at the very end of the component's returned JSX (after the closing `</Card>` of the table, i.e. immediately before the final `</div>\n  );\n}`):

```tsx
      {/* Add Standard Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-indigo-400" />
              Add Standard
            </DialogTitle>
            <DialogDescription>
              Manually add a standard from a body with no RSS feed (e.g. ASTM).
            </DialogDescription>
          </DialogHeader>

          {createError && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
              {createError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="std-reference">Reference Number</Label>
              <Input
                id="std-reference"
                placeholder="ASTM D638-14"
                value={createForm.iso_reference}
                onChange={(e) => setCreateForm((f) => ({ ...f, iso_reference: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="std-title">Title</Label>
              <Input
                id="std-title"
                placeholder="Standard Test Method for Tensile Properties of Plastics"
                value={createForm.title}
                onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="std-body">Standards Body</Label>
                <select
                  id="std-body"
                  value={createForm.standards_body}
                  onChange={(e) => setCreateForm((f) => ({ ...f, standards_body: e.target.value }))}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring text-foreground"
                >
                  {STANDARDS_BODY_OPTIONS.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="std-edition">Edition (optional)</Label>
                <Input
                  id="std-edition"
                  placeholder="2014"
                  value={createForm.edition ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, edition: e.target.value }))}
                />
              </div>
            </div>

            {createForm.standards_body === "Other" && (
              <div className="space-y-1.5">
                <Label htmlFor="std-body-other">Body name</Label>
                <Input
                  id="std-body-other"
                  placeholder="e.g. BSI, DIN"
                  value={otherBody}
                  onChange={(e) => setOtherBody(e.target.value)}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="std-committee">Committee / Working Group (optional)</Label>
                <Input
                  id="std-committee"
                  placeholder="D20"
                  value={createForm.tc_committee ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, tc_committee: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="std-published">Published date (optional)</Label>
                <Input
                  id="std-published"
                  type="date"
                  value={createForm.published_date ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, published_date: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="std-url">External URL (optional)</Label>
              <Input
                id="std-url"
                placeholder="https://www.astm.org/d0638-14.html"
                value={createForm.external_url ?? ""}
                onChange={(e) => setCreateForm((f) => ({ ...f, external_url: e.target.value }))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { setShowCreate(false); setCreateError(null); }}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                const body = createForm.standards_body === "Other" ? otherBody : createForm.standards_body;
                createMutation.mutate({
                  ...createForm,
                  standards_body: body,
                  edition: createForm.edition || undefined,
                  tc_committee: createForm.tc_committee || undefined,
                  published_date: createForm.published_date || undefined,
                  external_url: createForm.external_url || undefined,
                });
              }}
              disabled={
                createMutation.isPending ||
                !createForm.iso_reference ||
                !createForm.title ||
                (createForm.standards_body === "Other" && !otherBody)
              }
              className="gap-2"
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Add Standard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
```

- [ ] **Step 5: Verify — typecheck and live create**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: no errors.

```bash
docker compose logs frontend --tail=20
```
Expected: no new Vite errors after the file change (hot-reload picks it up automatically).

Then, with the full stack running, log in at `http://localhost:5173` as `admin@ists.local` / `Admin1234!`, go to Standards Library, confirm the "Add Standard" button appears, fill in a test ASTM standard, submit, and confirm it navigates to the new standard's detail page. Clean up the test standard afterward via `psql` (same as Task 3's verification).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/StandardsPage.tsx
git commit -m "feat: add manual standard creation modal to Standards Library"
```

---

### Task 7: Standards Body filter and badge display

**Files:**
- Modify: `frontend/src/pages/StandardsPage.tsx`

**Interfaces:**
- Consumes: `listStandardsBodies` (Task 5).

- [ ] **Step 1: Add the filter query and state**

Add `standardsBodyFilter` state right after the existing `stageFilter` state:

```tsx
  const [standardsBodyFilter, setStandardsBodyFilter] = useState("");
```

Add `standards_body: standardsBodyFilter || undefined` to the existing `queryParams` object:

```tsx
  const queryParams: StandardsListParams = {
    ...params,
    search: search.trim() || undefined,
    tc_committee: committeeFilter || undefined,
    standards_body: standardsBodyFilter || undefined,
    stage: stageFilter || undefined,
  };
```

Add the bodies query right after the existing `committees` query:

```tsx
  // Independent of the current page/filters, same reasoning as the
  // committees dropdown above.
  const { data: standardsBodies = [] } = useQuery({
    queryKey: ["standards", "standards-bodies"],
    queryFn: listStandardsBodies,
  });
```

Add `listStandardsBodies` to the existing `@/api/standards` import (already updated in Task 6's Step 1 above — if implementing Task 6 and Task 7 as genuinely separate PRs/sessions, add it here explicitly):

```typescript
import {
  createStandard, listCommittees, listStandards, listStandardsBodies,
  type StandardCreatePayload, type StandardGrouped, type StandardsListParams,
} from "@/api/standards";
```

- [ ] **Step 2: Add the filter dropdown to the filters row**

In the "Row 2" filters block, add a new dropdown right after the existing Committee dropdown's closing `</div>` and before the Stage dropdown:

```tsx
              {/* Standards Body dropdown */}
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Body</p>
                <div className="relative">
                  <select
                    value={standardsBodyFilter}
                    onChange={(e) => {
                      setStandardsBodyFilter(e.target.value);
                      setParams((p) => ({ ...p, page: 1 }));
                    }}
                    className="appearance-none min-w-[140px] cursor-pointer rounded-lg border border-slate-600 bg-slate-900 px-4 py-2 pr-8 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">All Bodies</option>
                    {standardsBodies.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>
              </div>
```

- [ ] **Step 3: Show it as a badge in the table**

In the primary row's Title cell, right after the existing `is_purchased` badge block, add a Standards Body badge:

```tsx
                    <TableCell className="max-w-xs">
                      <p className="truncate text-foreground">{std.title}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {std.standards_body && (
                          <Badge variant="secondary" className="text-[9px] py-0 px-1.5">
                            {std.standards_body}
                          </Badge>
                        )}
                        {std.is_purchased && (
                          <span className="inline-flex items-center bg-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30">
                            ✓ Purchased
                          </span>
                        )}
                      </div>
                    </TableCell>
```

(This replaces the existing Title `<TableCell>` block, which currently wraps the purchased badge directly under the title `<p>` without an enclosing flex row — the change wraps both badges in one `flex` row so they sit side by side instead of stacking awkwardly.)

- [ ] **Step 4: Verify — typecheck and live filter check**

```bash
cd frontend && npx tsc --noEmit -p .
```
Expected: no errors.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@ists.local","password":"Admin1234!"}' | python -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
curl -s "http://localhost:8000/api/v1/standards/standards-bodies" -H "Authorization: Bearer $TOKEN"
```
Expected: same distinct-bodies list confirmed in Task 4 — the frontend dropdown will be populated from this same endpoint.

Then, in the browser, open Standards Library → Filters, confirm the "Body" dropdown appears between Committee and Stage, select "ISO", and confirm the list narrows and every visible row shows an "ISO" badge next to its title.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/StandardsPage.tsx
git commit -m "feat: add Standards Body filter and badge display"
```
