# Manual Standard Entry & Standards Body Field

## Context

Today every row in `standards` is created exclusively by `app.tasks.feeds._process_entry()`,
which parses ISO/IEC/IEEE RSS feeds (`app/tasks/feeds.py`'s `_REFERENCE_RE`). There is no
create endpoint, no create schema, and no "Add Standard" UI anywhere — `standard_service.py`
is entirely read/update (list, get, purchase). The library now also needs to track ASTM and
other standards bodies that don't publish RSS feeds, so a manager/admin needs a way to add a
standard by hand.

There is also currently no field anywhere that records which body a standard belongs to.
The only signal is the `iso_reference` string itself (e.g. "ISO 9001:2015" vs "ASTM D638-14"),
and `tc_committee` ("Technical Committee") is an ISO/IEC-specific concept that doesn't apply to
ASTM. This spec adds both: a `standards_body` field, and a manual-entry flow for
admins/managers.

Scope is backend + frontend for standard **creation** only. Editing existing standards
(feed-sourced or manual) is explicitly out of scope — see "Out of scope" below.

## Decisions (user-confirmed)

- **Standards Body field**: added as a new field on `Standard`, not left implicit in the
  reference text.
- **Field shape**: a plain string column (not a Postgres enum), because the frontend picker is
  "fixed dropdown (ISO/IEC/IEEE/ASTM) + an 'Other' option with free text" — an enum would
  reject exactly the values "Other" exists to allow.
- **Creation flow**: two separate steps. "Add Standard" creates only the metadata record;
  its document (if any) is uploaded afterward via the existing Documents tab on the standard's
  detail page — reusing the upload flow (and its automatic AI tagging) rather than duplicating it.
- **Permissions**: manager + admin, matching the existing permission level for document upload
  and marking a standard as purchased.
- **Edit scope**: create-only in this pass. Editing existing standards (including correcting
  feed-sourced ones) is a reasonable follow-up but has its own open questions (should an edit to
  a feed-sourced standard write a history event? can you edit a field the next feed poll would
  overwrite anyway?) that deserve their own design pass.
- **Standards Body for feed-sourced standards too**: not manual-entry-only. The feed parser
  already extracts the org prefix (ISO/IEC/IEEE) from every reference it parses — reused to
  populate `standards_body` on every newly-discovered standard as well, plus a one-time backfill
  script for existing rows (same pattern as the existing `backfill_base_reference.py`).
- **Notifications on manual creation**: yes — dispatches the same `send_bulk_notification`
  (`event_type="new"`) that a feed-discovered standard triggers. A new standard entering the
  library notifies the same way regardless of how it got there.

## Data model

New migration `0012_add_standards_body.py` (current head is `0011_add_document_tags.py`):

```python
op.add_column('standards', sa.Column(
    'standards_body', sa.String(50), nullable=True,
    comment="Issuing body (ISO, IEC, IEEE, ASTM, or free text via 'Other') — "
            "populated for both feed-sourced and manually-created standards."
))
op.create_index('ix_standards_standards_body', 'standards', ['standards_body'])
```

`app/models/standard.py`: add `standards_body: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)`.

No new enum, no `create_type=False` dance needed — this is intentionally NOT a Postgres enum
(see Decisions above).

## Feed ingestion changes (`backend/app/tasks/feeds.py`)

`parse_iso_entry()` already derives `org_part` (e.g. `"ISO"`, `"ISO/WD"`, `"IEC/TS"`,
`"ISO/IEC/IEEE"`) from the matched reference before building `iso_reference`. Add one line to
its returned dict:

```python
"standards_body": org_part.split("/")[0].strip(),
```

This takes the leading org token — `"ISO/WD"` → `"ISO"`, `"IEC/TS"` → `"IEC"`,
`"ISO/IEC/IEEE"` → `"ISO"` — which is exactly the set of values the frontend's fixed dropdown
offers, so feed-sourced and manually-entered standards end up using the same vocabulary.

`_process_entry()`: set `standard.standards_body = parsed["standards_body"]` in both the
new-standard branch and the update branch (alongside the other `parsed[...]` field
assignments already there) — keeps it in sync the same way `title`/`stage`/`tc_committee`
already are.

## Backfill script

New `backend/scripts/backfill_standards_body.py`, following `backfill_base_reference.py`'s
exact shape:

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

sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.standard import Standard
from app.tasks.feeds import _REFERENCE_RE

setup_logging()
log = structlog.get_logger(__name__)


def _derive_standards_body(iso_reference: str) -> str | None:
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

Reuses `_REFERENCE_RE` directly from `app.tasks.feeds` (same import pattern the base_reference
backfill script already uses for `_extract_base_reference`) — guarantees the backfill produces
identical values to what live feed ingestion produces for the same reference shapes. Standards
whose reference doesn't match the ISO/IEC/IEEE pattern (there shouldn't be any pre-existing ones,
since manual entry — the only source of non-ISO references — doesn't exist until this feature
ships) are left `NULL`, same as any row where the field genuinely doesn't apply.

## Backend API

### Schema additions (`backend/app/schemas/standard.py`)

Add `standards_body: str | None = None` to `StandardListItem` and `StandardDetail` (so it
flows through to `StandardGrouped`/`StandardDetailWithAmendments` automatically, since those
subclass them).

New creation schema:

```python
class StandardCreate(BaseModel):
    iso_reference: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1)
    standards_body: str = Field(..., min_length=1, max_length=50)
    edition: str | None = Field(default=None, max_length=50)
    tc_committee: str | None = Field(default=None, max_length=100)
    status: StandardStatus = StandardStatus.active
    published_date: date | None = None
    external_url: str | None = None
```

### Service (`backend/app/services/standard_service.py`)

New `create_standard_manually()`:

```python
async def create_standard_manually(
    payload: StandardCreate,
    actor_id: uuid.UUID,
    db: AsyncSession,
) -> Standard:
    """
    Create a standard by hand (admin/manager data entry), not via RSS discovery.

    Raises ConflictError if iso_reference already exists.
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
        # source_feed_id, content_hash stay NULL — this standard has no feed origin
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

`_extract_base_reference` is reused as-is (already ISO/IEC/IEEE-shape-aware). For a reference
shape it doesn't recognize (e.g. an ASTM designation), its existing fallback returns the input
string unchanged — this is pre-existing behavior, not new — which still behaves correctly for
grouping purposes: that standard simply won't share a group with anything else, exactly like
any other standard with no computable base reference.

### Endpoint (`backend/app/api/v1/standards.py`)

Note: this file's current top-level import is `from fastapi import APIRouter, Query` — no
`status` — since no existing route in it sets an explicit `status_code`. Add `status` to that
import for the `status.HTTP_201_CREATED` below. Also add `StandardCreate` to the existing
`from app.schemas.standard import (...)` import block.

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

Same commit-then-dispatch ordering already used by `purchase_standard` in this same file —
notifications only fire once the row is durably committed.

### Filtering

`list_standards()` / `get_grouped_standards()` gain a `standards_body: str | None` exact-match
filter parameter, threaded through exactly like the existing `tc_committee` filter (both the
SQL path and the `_matches_filters()` in-memory path). The `GET /standards` route gains a
matching `standards_body: str | None = Query(default=None)` parameter.

A new `GET /standards/standards-bodies` endpoint (mirroring the existing
`GET /standards/committees`) returns the distinct set of `standards_body` values across all
standards, for the frontend filter dropdown — registered before the `/{standard_id}` route,
same reasoning as the existing `/committees` route's placement.

## Frontend

### API client (`frontend/src/api/standards.ts`)

- Add `standards_body: string | null` to `Standard`/`StandardDetail`/`StandardGrouped`
  interfaces.
- Add `standards_body?: string` to `StandardsListParams`.
- New `createStandard(payload): Promise<StandardDetail>` calling `POST /api/v1/standards`.
- New `listStandardsBodies(): Promise<string[]>` calling `GET /api/v1/standards/standards-bodies`.

### "Add Standard" modal (`StandardsPage.tsx`)

New button in the page header, visible to `isAdmin || isManager` only, opening a `Dialog` —
same structural pattern as `FeedsPage.tsx`'s "Add Feed" modal. Fields: Reference Number*,
Title*, Standards Body* (dropdown: ISO / IEC / IEEE / ASTM / Other — selecting "Other" reveals
a text input for the free-text value), Committee/Working Group (optional), Edition (optional),
Status (dropdown, defaults to Active), Published Date (optional), External URL (optional). On
successful creation, navigate to `/standards/{new_id}` — the natural next step is uploading its
document from the Documents tab there.

### Filtering & display

- Standards Body becomes a new filter control alongside the existing Committee/Stage filters,
  backed by `listStandardsBodies()` for its options (same pattern as the existing Committee
  dropdown, which is backed by `listCommittees()`).
- Displayed as a small `Badge` (reusing the existing component, `variant="secondary"` — no new
  per-body color coding, that's cosmetic polish for a later pass) next to the reference/title in
  the Standards Library table and on the standard detail page.

## Error handling & edge cases

- Duplicate `iso_reference` on creation → `409 Conflict` via the existing `ConflictError`
  exception path (same JSON error shape as every other conflict in this API).
- A standard with an unrecognized reference shape (any non-ISO/IEC/IEEE format, e.g. ASTM) gets
  `base_reference` equal to its own raw reference string (existing `_extract_base_reference`
  fallback) — it simply doesn't group with anything, which is the correct behavior, not a bug
  to work around.
- `content_hash` and `source_feed_id` stay `NULL` for manually-created standards — both columns
  are already nullable specifically for this case (`content_hash`'s docstring already says
  "Nullable because standards created before M2 (or manually) have no hash").
- If an admin manually creates a standard whose reference *does* happen to match the
  ISO/IEC/IEEE pattern (nothing stops them from manually adding an ISO standard too), it behaves
  identically to a feed-discovered one from that point forward — grouping, base_reference, and
  future feed updates against the same `iso_reference` all work the same way, since none of
  those code paths distinguish by `source_feed_id`.

## Out of scope (explicitly deferred)

- Editing existing standards (manual or feed-sourced) — a separate feature with its own
  questions about interaction with feed updates and history semantics.
- Per-standards-body badge color coding — cosmetic, not required for the core need (telling
  bodies apart), fine as flat `secondary` badges for now.
- Bulk/CSV import of multiple standards at once — this spec covers one-at-a-time manual entry
  only.
- Combined create+upload in a single form — explicitly rejected in favor of reusing the
  existing upload flow unmodified.
