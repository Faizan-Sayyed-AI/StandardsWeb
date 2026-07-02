# Group by Base Reference with Expandable Versions

## Context

The Standards Library list (`frontend/src/pages/StandardsPage.tsx`) shows one row per
`Standard` row in the database. Pre-publication draft/stage variants of the same
standard number — e.g. `ISO/WD 3651-2`, `ISO/CD 3651-2`, `ISO 3651-2:1998` — are
currently unrelated rows with no visual link between them, even though they represent
the evolving history of one standard. This feature groups such rows by a derived
"base reference" (the bare numeric designation, e.g. `3651-2`) and lets the primary
(most recent) row expand to reveal the others inline.

Backend and DB changes only; no changes to the pending change-history-timeline work.

## Relationship to the existing amendment mechanism

The app already links amendments/corrigenda to their base standard via
`parent_standard_id` (set in `feeds.py`'s `_get_parent_reference`/`_AMD_SUFFIX_RE`),
surfaced today as the "Amendments & Corrigenda" card on the standard detail page.

Tracing the new `_extract_base_reference()` regex by hand: `"ISO 27874:2008/CD Amd 1"`
→ `base_reference = "27874"`, same as its parent `"ISO 27874:2008"`. Left unguarded,
amendment rows would also surface as "versions" in the new grouped list, duplicating
the Amendments card.

**Decision (user-confirmed):** amendment rows (`parent_standard_id IS NOT NULL`) are
excluded from grouping entirely — not shown as a version under another row, and not
grouped among themselves either. They continue to appear exactly as today: as their
own standalone row in the ungrouped sense, and on their parent's Amendments card.
Grouping only ever considers rows where `parent_standard_id IS NULL`.

## Step 1 — `_extract_base_reference()` in `backend/app/tasks/feeds.py`

Added immediately after `_EDITION_RE`, exactly as specified by the user. Verified by
hand against all 7 worked examples in the docstring, including the AMD-suffix case
(the colon in `27874:2008/AMD...` stops the digit/hyphen/dot capture before the org
suffix is ever reached, so no special-casing of AMD/COR is needed in the regex).

```python
def _extract_base_reference(iso_reference: str) -> str:
    text = re.sub(
        r'^(?:ISO|IEC|IEEE)(?:/(?:IEC|IEEE|TS|TR|WD|AWI|CD|NP|PAS|GUIDE))*\s*(?:TS|TR|WD|AWI|CD|NP|PAS|GUIDE)?\s*',
        '', iso_reference, flags=re.IGNORECASE
    ).strip()
    m = re.match(r'^([\d][\d\-\.]*)', text)
    return m.group(1) if m else iso_reference
```

**Known limitation, accepted as-is:** the regex strips the org prefix, so a
same-numbered standard from two different orgs (hypothetically `ISO 9001` vs a
differently-scoped `IEC 9001`) would collide into one group. Not a concern in this
dataset (ISO/IEC dual-logo standards sharing a number is the norm and should group),
but noted here since it's a real edge case, not an oversight.

## Step 2 — Migration `0007_add_base_reference.py`

`down_revision = "0006"` (current alembic head, confirmed live). `upgrade()`/
`downgrade()` exactly as specified — nullable `String(50)` column + index.

## Step 3 — ORM model

`base_reference: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)`
added to `backend/app/models/standard.py`, matching the column's existing style
(see `stage_code`, `content_hash` for precedent).

## Step 4 — Backfill + wiring

- `backend/app/tasks/feeds.py`'s `_process_entry()`: `standard.base_reference =
  _extract_base_reference(iso_ref)` set on both the INSERT branch (right after
  constructing the new `Standard(...)`) and the UPDATE branch (alongside the other
  `standard.<field> = ...` assignments before the second history-append block).
- `backend/scripts/backfill_base_reference.py` (new): follows the existing
  `scripts/seed.py` pattern — `sys.path.insert(0, "/app")`, `async_session_factory`,
  `asyncio.run(...)`. Loads all standards, sets `base_reference` via the same helper
  (imported from `app.tasks.feeds`), commits once, prints a count.

## Step 5 — Backend API: grouped endpoint

**Schemas** (`backend/app/schemas/standard.py`), as specified plus one addition:

```python
class StandardVersion(BaseModel):
    id: uuid.UUID
    iso_reference: str
    stage_code: str | None
    stage_name: str | None
    status: str
    published_date: date | None
    edition: str | None
    is_purchased: bool
    model_config = ConfigDict(from_attributes=True)

class StandardGrouped(StandardListItem):
    base_reference: str | None = None   # ADDED — frontend needs this to key expandedGroups
    versions: list[StandardVersion] = []
    versions_count: int = 0
```

**`GET /api/v1/standards`** gains `grouped: bool = Query(default=True)`. When
`grouped=false`, behavior is byte-for-byte identical to today (existing
`list_standards` path, response model `Page[StandardListItem]`). When `grouped=true`
(default), delegates to the new service function and responds
`Page[StandardGrouped]`.

**`get_grouped_standards()` in `standard_service.py`** — algorithm:

1. Build the same filter conditions as `list_standards` (search/status/committee/
   is_purchased), plus the mandatory `Standard.parent_standard_id.is_(None)`.
2. Execute the query **unpaginated** — fetch every matching row. (918 standards
   total today; fetching all rows and grouping in Python is simple and fast at this
   scale. Revisit only if the table grows by orders of magnitude.)
3. Group the fetched rows by `base_reference` in Python (`None`/empty
   `base_reference` — shouldn't occur post-backfill, but if it does, each such row is
   its own singleton group keyed by its own `id` so it still renders as a normal row).
4. Per group, pick the primary = the row with the most recent `published_date` (`None`
   published_date sorts last, so a group of all-`None` dates just keeps insertion
   order — fine, matches "most recent" intent when no dates exist).
5. **Filter semantics (confirmed, literal reading of "filters apply to the primary row
   only"):** a group is kept iff its primary satisfies the original filter
   conditions, evaluated in Python against the primary object's fields (search
   against `iso_reference`/`title`/`tc_committee` substrings, status equality, etc,
   mirroring the SQL conditions built in step 1). Non-primary versions inside a kept
   group are never filtered out individually — they ride along even if they wouldn't
   individually match.
6. Sort the surviving groups by the requested `sort_by`/`sort_order`, applied to each
   group's primary.
7. Paginate the **group list** (not rows) by `page`/`page_size`; `Page.total` = number
   of surviving groups.
8. Map each surviving, paginated group to `StandardGrouped`: primary's fields +
   `base_reference` + `versions` (the group's other members, `StandardVersion.
  model_validate`'d) + `versions_count` (total group size, primary included). Singleton
   groups get `versions = []`, `versions_count = 1`.

## Step 6 — Frontend

**`frontend/src/api/standards.ts`**:
- `StandardsListParams` gains `grouped?: boolean`.
- New `StandardVersion` and `StandardGrouped` interfaces mirroring the backend
  schemas.
- `listStandards()` return type becomes `Promise<Page<StandardGrouped>>` (a superset
  of the plain `Standard` shape — safe for `grouped=false` callers too, since they
  simply won't see `versions`/`versions_count`/`base_reference` populated meaningfully,
  and don't reference those fields).

**`frontend/src/pages/DashboardPage.tsx`**: its existing `listStandards({ page: 1,
page_size: 8, sort_by: "updated_at", sort_order: "desc" })` call gains
`grouped: false`, to keep the "recent standards" widget showing 8 individual rows
exactly as it does today — it's the only other consumer of this endpoint and isn't
part of this feature's scope.

**`frontend/src/pages/StandardsPage.tsx`** — as specified:
- `expandedGroups: Set<string>` state (keyed by `base_reference`), `toggleGroup()`.
- Primary row: unchanged layout; when `versions_count > 1`, an expand control at the
  far left of the row, before the Reference column — collapsed: `▶` + `+N versions`
  badge (`bg-slate-700 text-slate-300`); expanded: `▼` + badge recolored
  (`bg-indigo-500/20 text-indigo-300`). `N = versions_count - 1`. When
  `versions_count === 1`, no control, no badge — row is pixel-identical to today.
- Expanded version rows render directly below the primary when its group is in
  `expandedGroups`: `border-l-2 border-indigo-500/30 ml-4`, `bg-slate-800/40`,
  `transition-all duration-200`. Columns shown: Reference, Stage badge, Status badge,
  Stage Date only (Title/Committee/Edition/Updated omitted — same title/committee as
  the primary, and edition/updated aren't useful at a glance for a version list).
  Each version row is clickable and navigates to `/standards/{version.id}`.

## Step 7 — Deploy commands (as specified)

```
docker compose exec web alembic upgrade head
docker compose exec web python scripts/backfill_base_reference.py
docker compose stop worker && docker compose start worker
docker compose stop web && docker compose start web
```

(`docker compose restart` is never used — confirmed hangs on this Windows host per
existing project notes. Migration files `0001`–`0006` are not touched. `NullPool` in
`database.py` for Celery DB connections is not touched.)

## Testing plan

No backend/frontend test suite exists in this repo (confirmed in an earlier session).
Manual verification:

- Run the SQL grouping query from the task description against the live DB post-backfill;
  expect the `3651-2` group (or whichever base numbers actually have multiple
  variants in this dataset) to show multiple `iso_reference` values via `STRING_AGG`.
- `GET /api/v1/standards` (default `grouped=true`) — inspect a multi-version group's
  JSON: `versions_count` matches the SQL group count, `versions` excludes the primary,
  amendment rows never appear inside `versions`.
- `GET /api/v1/standards?grouped=false` — byte-for-byte matches pre-feature response
  shape.
- UI: multi-version group shows the collapsed badge; clicking expands with the
  correct styling; clicking a version row navigates to that version's own detail
  page; collapsing works; all existing filters/search/sort continue to behave now
  that they're being evaluated in Python against primaries.
- Dashboard's "recent standards" widget still shows 8 individual rows, unaffected.
