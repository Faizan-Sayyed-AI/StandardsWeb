"""
Standards read service (M3).

All endpoints are read-only in M3. Write operations (purchase, status change)
are added in M4/M6. Supports filtered, sorted, paginated list queries.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.core.iso_stages import is_draft_stage
from app.models.document import Document
from app.models.document_tag import DocumentTag
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import StandardHistory
from app.schemas.standard import StandardCreate, StandardGrouped, StandardListItem, StandardVersion

log = structlog.get_logger(__name__)


def _stage_matches_sql(stage_filter: str, entity=Standard):
    """
    Build the SQLAlchemy condition for a stage filter.

    A filter ending in ".x" (e.g. "20.x") means "any stage in this phase" —
    matched as a prefix. Anything else is an exact stage_code match. Mirrors
    the frontend's matchesStageFilter() semantics in StandardsPage.tsx.

    `entity` allows applying the filter to an aliased Standard (grouped path).
    """
    if stage_filter.endswith(".x"):
        prefix = stage_filter[:-1]  # "20.x" -> "20."
        return entity.stage_code.like(f"{prefix}%")
    return entity.stage_code == stage_filter


async def list_standards(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: StandardStatus | None = None,
    tc_committee: str | None = None,
    standards_body: str | None = None,
    stage: str | None = None,
    is_purchased: bool | None = None,
    sort_by: str = "updated_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> tuple[list[Standard], int]:
    """
    Return a filtered, sorted, paginated list of standards.

    Args:
        search:       Free-text search across iso_reference and title.
        status:       Filter by StandardStatus enum value.
        tc_committee: Exact match on tc_committee field.
        standards_body: Exact match on standards_body field.
        stage:        Exact stage_code match, or a ".x" phase prefix (e.g. "20.x").
        is_purchased: Filter by purchase flag.
        sort_by:      Column name — one of: iso_reference, title, updated_at, status.
        sort_order:   'asc' or 'desc'.

    Returns:
        (standards, total_matching_count)
    """
    # Build base query
    query = select(Standard)

    # Apply filters
    conditions = []
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
    if status is not None:
        conditions.append(Standard.status == status)
    if tc_committee is not None:
        conditions.append(Standard.tc_committee == tc_committee)
    if standards_body is not None:
        conditions.append(Standard.standards_body == standards_body)
    if stage:
        conditions.append(_stage_matches_sql(stage))
    if is_purchased is not None:
        conditions.append(Standard.is_purchased == is_purchased)

    if conditions:
        from sqlalchemy import and_
        query = query.where(and_(*conditions))

    # Count total matching rows
    count_query = select(func.count()).select_from(query.subquery())
    total: int = (await db.execute(count_query)).scalar_one()

    # Apply sorting
    sort_column_map = {
        "iso_reference": Standard.iso_reference,
        "title": Standard.title,
        "updated_at": Standard.updated_at,
        "status": Standard.status,
        "created_at": Standard.created_at,
        "published_date": Standard.published_date,
    }
    sort_col = sort_column_map.get(sort_by, Standard.updated_at)
    # id tie-break keeps pagination stable when the sort column has ties (e.g.
    # bulk-imported rows sharing one updated_at) — same reason as the grouped
    # path. Without it, page membership shifts nondeterministically between
    # requests, so a row can appear on two pages or none.
    if sort_order == "desc":
        query = query.order_by(sort_col.desc(), Standard.id)
    else:
        query = query.order_by(sort_col.asc(), Standard.id)

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    standards = list(result.scalars().all())
    return standards, total


async def get_grouped_standards(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: StandardStatus | None = None,
    tc_committee: str | None = None,
    standards_body: str | None = None,
    stage: str | None = None,
    is_purchased: bool | None = None,
    sort_by: str = "updated_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> tuple[list[StandardGrouped], int]:
    """
    Return standards grouped by base_reference, with pre-publication draft/stage
    variants of the same number collapsed into one primary row plus a versions list.

    Amendment/corrigendum rows (parent_standard_id IS NOT NULL) never participate in
    grouping — they're excluded entirely, since they already have their own dedicated
    UI (the Amendments card on the parent standard's detail page).

    Filters apply only to whether a group's primary matches — a kept group's other
    versions ride along unfiltered.

    Everything happens in SQL: DISTINCT ON picks each group's primary (latest
    published_date, NULLs lowest, id as tie-break), filters/sort/pagination run
    over those primaries, and one second bounded query fetches the page's other
    versions. The table is never fully loaded into memory.
    """
    # Rows with no base_reference are each their own singleton group keyed by id.
    # nullif(base_reference, '') folds an empty string into the NULL case, so a
    # blank base_reference (e.g. from a backfill/import) yields a singleton group
    # instead of collapsing every such row into one shared '' group.
    group_key = func.coalesce(
        func.nullif(Standard.base_reference, ""), cast(Standard.id, String)
    )
    primary_sq = (
        select(Standard)
        .where(Standard.parent_standard_id.is_(None))
        .distinct(group_key)
        .order_by(group_key, Standard.published_date.desc().nulls_last(), Standard.id)
        .subquery("group_primaries")
    )
    primary = aliased(Standard, primary_sq)

    conditions = []
    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            or_(
                primary.iso_reference.ilike(search_term),
                primary.title.ilike(search_term),
                primary.tc_committee.ilike(search_term),
                primary.id.in_(
                    select(Document.standard_id)
                    .join(DocumentTag, DocumentTag.document_id == Document.id)
                    .where(DocumentTag.search_text.ilike(search_term))
                ),
            )
        )
    if status is not None:
        conditions.append(primary.status == status)
    if tc_committee is not None:
        conditions.append(primary.tc_committee == tc_committee)
    if standards_body is not None:
        conditions.append(primary.standards_body == standards_body)
    if stage:
        conditions.append(_stage_matches_sql(stage, primary))
    if is_purchased is not None:
        conditions.append(primary.is_purchased == is_purchased)

    query = select(primary)
    if conditions:
        query = query.where(*conditions)

    total: int = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()

    sort_column_map = {
        "iso_reference": primary.iso_reference,
        "title": primary.title,
        "updated_at": primary.updated_at,
        # Sorting by status orders by the Postgres native-enum declaration order
        # (not alphabetical). This is intentionally the same as the flat
        # list_standards path, so grouped and flat views stay consistent.
        "status": primary.status,
        "created_at": primary.created_at,
        "published_date": primary.published_date,
    }
    sort_col = sort_column_map.get(sort_by, primary.updated_at)
    # NULLs sort as the smallest value (the UI treats "no date" as oldest).
    # id tie-break keeps pagination stable: bulk-imported rows share one
    # updated_at, so without it page membership shifts between requests.
    if sort_order == "desc":
        query = query.order_by(sort_col.desc().nulls_last(), primary.id)
    else:
        query = query.order_by(sort_col.asc().nulls_first(), primary.id)

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    primaries = list((await db.execute(query)).scalars().all())

    # Second bounded query: every non-amendment member of the page's groups.
    versions_map: dict[str, list[Standard]] = {}
    group_refs = [p.base_reference for p in primaries if p.base_reference]
    if group_refs:
        members_result = await db.execute(
            select(Standard)
            .where(
                Standard.parent_standard_id.is_(None),
                Standard.base_reference.in_(group_refs),
            )
            .order_by(Standard.published_date.desc().nulls_last(), Standard.id)
        )
        for member in members_result.scalars():
            versions_map.setdefault(member.base_reference, []).append(member)

    grouped: list[StandardGrouped] = []
    for p in primaries:
        members = versions_map.get(p.base_reference, []) if p.base_reference else []
        versions = [m for m in members if m.id != p.id]
        grouped.append(
            StandardGrouped(
                **StandardListItem.model_validate(p).model_dump(),
                base_reference=p.base_reference,
                versions=[StandardVersion.model_validate(v) for v in versions],
                versions_count=len(versions) + 1,
            )
        )

    return grouped, total


async def list_committees(db: AsyncSession) -> list[str]:
    """Return the distinct set of tc_committee values across all standards, for filter dropdowns."""
    result = await db.execute(
        select(Standard.tc_committee)
        .where(Standard.tc_committee.is_not(None))
        .distinct()
        .order_by(Standard.tc_committee.asc())
    )
    return [row[0] for row in result.all()]


async def list_standards_bodies(db: AsyncSession) -> list[str]:
    """Return the distinct set of standards_body values across all standards, for filter dropdowns."""
    result = await db.execute(
        select(Standard.standards_body)
        .where(Standard.standards_body.is_not(None))
        .distinct()
        .order_by(Standard.standards_body.asc())
    )
    return [row[0] for row in result.all()]


async def get_standard(standard_id: uuid.UUID, db: AsyncSession) -> Standard:
    """Fetch a single standard by UUID. Raises NotFoundError if missing."""
    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")
    return standard


DRAFT_BLOCKED_REASON = (
    "Not available — standard is still at draft stage ({stage}). "
    "Available once published."
)
NO_DOCUMENT_BLOCKED_REASON = (
    "Upload the standard document before marking it as purchased."
)


def _stage_label(standard: Standard) -> str:
    """Human-readable stage for a blocked-reason message."""
    return " ".join(
        p for p in (standard.stage_code, standard.stage_name) if p
    ) or "pre-publication"


def draft_blocked_reason(standard: Standard) -> str:
    """
    The user-facing reason a draft standard cannot be uploaded to or purchased.

    Shared by the purchase guard, the upload guard, and get_purchasability so
    the three can never disagree on the wording.
    """
    return DRAFT_BLOCKED_REASON.format(stage=_stage_label(standard))


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
        reason = draft_blocked_reason(standard)
    elif document_count == 0 and not standard.is_purchased:
        reason = NO_DOCUMENT_BLOCKED_REASON

    return {
        "is_draft": draft,
        "document_count": document_count,
        "can_upload": can_upload,
        "can_purchase": can_purchase,
        "purchase_blocked_reason": reason,
    }


async def get_amendments(standard_id: uuid.UUID, db: AsyncSession) -> list[Standard]:
    """Return all child standards (amendments/corrigenda) linked to this parent."""
    result = await db.execute(
        select(Standard)
        .where(Standard.parent_standard_id == standard_id)
        .order_by(Standard.iso_reference.asc())
    )
    return list(result.scalars().all())


async def get_standard_history(
    standard_id: uuid.UUID,
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[StandardHistory], int]:
    """
    Return paginated change history for a standard (newest first).
    Raises NotFoundError if the standard doesn't exist.
    """
    # Verify standard exists
    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")

    count_result = await db.execute(
        select(func.count(StandardHistory.id)).where(
            StandardHistory.standard_id == standard_id
        )
    )
    total: int = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        select(StandardHistory)
        .where(StandardHistory.standard_id == standard_id)
        .order_by(StandardHistory.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    history = list(result.scalars().all())
    return history, total


async def purchase_standard(
    standard_id: uuid.UUID,
    actor_id: uuid.UUID,
    purchase_notes: str | None,
    db: AsyncSession,
) -> tuple[Standard, bool]:
    """
    Mark standard as purchased, append standard history row, write audit log.

    Returns (standard, newly_purchased) — newly_purchased is False when the
    standard was already purchased, so callers (the API router) know not to
    re-dispatch a "purchased" notification broadcast on a no-op call.
    """
    import datetime
    from app.models.standard_history import EventSource, EventType, StandardHistory
    from app.services.audit_service import write_audit_log

    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")

    if standard.is_purchased:
        # Already purchased — a double-click or client retry shouldn't
        # re-append history or re-broadcast a "purchased" notification to
        # every active user.
        return standard, False

    # Order matters: the already-purchased no-op above stays first, so a
    # repeat call remains idempotent rather than turning into a 422.
    if is_draft_stage(standard.stage_code):
        raise AppValidationError(draft_blocked_reason(standard))

    doc_count = await db.execute(
        select(func.count(Document.id)).where(
            Document.standard_id == standard.id,
            Document.is_current == True,  # noqa: E712
        )
    )
    if doc_count.scalar_one() == 0:
        raise AppValidationError(NO_DOCUMENT_BLOCKED_REASON)

    old_snapshot = {
        "is_purchased": standard.is_purchased,
        "purchased_at": standard.purchased_at.isoformat() if standard.purchased_at else None,
        "purchased_by": str(standard.purchased_by) if standard.purchased_by else None,
        "purchase_notes": standard.purchase_notes,
    }

    standard.is_purchased = True
    standard.purchased_at = datetime.datetime.now(datetime.timezone.utc)
    standard.purchased_by = actor_id
    standard.purchase_notes = purchase_notes

    new_snapshot = {
        "is_purchased": True,
        "purchased_at": standard.purchased_at.isoformat(),
        "purchased_by": str(actor_id),
        "purchase_notes": purchase_notes,
    }

    history = StandardHistory(
        standard_id=standard.id,
        event_type=EventType.purchased,
        old_value=old_snapshot,
        new_value=new_snapshot,
        source=EventSource.manual,
        triggered_by=actor_id,
        notes="Standard purchased manually",
    )
    db.add(history)
    await db.flush()
    await db.refresh(standard)

    # Audit log
    await write_audit_log(
        db,
        action="standard.purchased",
        resource_type="standard",
        actor_id=actor_id,
        resource_id=standard.id,
        payload={
            "iso_reference": standard.iso_reference,
            "purchase_notes": purchase_notes,
        }
    )

    log.info("standard_purchased", standard_id=str(standard_id), actor_id=str(actor_id))
    return standard, True


async def create_standard_manually(
    payload: StandardCreate,
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

