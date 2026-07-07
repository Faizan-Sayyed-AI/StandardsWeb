"""
Standards read service (M3).

All endpoints are read-only in M3. Write operations (purchase, status change)
are added in M4/M6. Supports filtered, sorted, paginated list queries.
"""

import uuid
from datetime import date
from typing import Literal

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.models.document_tag import DocumentTag
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import StandardHistory
from app.schemas.standard import StandardGrouped, StandardListItem, StandardVersion

log = structlog.get_logger(__name__)


def _stage_matches_sql(stage_filter: str):
    """
    Build the SQLAlchemy condition for a stage filter.

    A filter ending in ".x" (e.g. "20.x") means "any stage in this phase" —
    matched as a prefix. Anything else is an exact stage_code match. Mirrors
    the frontend's matchesStageFilter() semantics in StandardsPage.tsx.
    """
    if stage_filter.endswith(".x"):
        prefix = stage_filter[:-1]  # "20.x" -> "20."
        return Standard.stage_code.like(f"{prefix}%")
    return Standard.stage_code == stage_filter


def _stage_matches(stage_code: str | None, stage_filter: str | None) -> bool:
    """Python equivalent of _stage_matches_sql, for the in-memory grouped-standards path."""
    if not stage_filter:
        return True
    if not stage_code:
        return False
    if stage_filter.endswith(".x"):
        return stage_code.startswith(stage_filter[:-1])
    return stage_code == stage_filter


async def list_standards(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: StandardStatus | None = None,
    tc_committee: str | None = None,
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
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    standards = list(result.scalars().all())
    return standards, total


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


async def get_grouped_standards(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: StandardStatus | None = None,
    tc_committee: str | None = None,
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
    versions ride along unfiltered. Grouping and pagination are done in Python because
    a group split across two row-pages would be broken; this is fine at this table's
    scale (fetches all non-amendment rows once per call).
    """
    result = await db.execute(
        select(Standard).where(Standard.parent_standard_id.is_(None))
    )
    all_standards = list(result.scalars().all())

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

    # Group by base_reference. Rows with no base_reference (shouldn't happen
    # post-backfill) are each their own singleton group keyed by their own id.
    groups: dict[str, list[Standard]] = {}
    for s in all_standards:
        key = s.base_reference or f"__singleton__{s.id}"
        groups.setdefault(key, []).append(s)

    def _primary(members: list[Standard]) -> Standard:
        return max(
            members,
            key=lambda s: s.published_date or date.min,
        )

    kept: list[tuple[str, Standard, list[Standard]]] = []
    for key, members in groups.items():
        primary = _primary(members)
        if not _matches_filters(
            primary,
            search=search,
            status=status,
            tc_committee=tc_committee,
            stage=stage,
            is_purchased=is_purchased,
            tag_matched_ids=tag_matched_ids,
        ):
            continue
        versions = [m for m in members if m.id != primary.id]
        kept.append((key, primary, versions))

    sort_key_map = {
        "iso_reference": lambda t: t[1].iso_reference,
        "title": lambda t: t[1].title,
        "updated_at": lambda t: t[1].updated_at,
        "status": lambda t: t[1].status.value,
        "created_at": lambda t: t[1].created_at,
        "published_date": lambda t: t[1].published_date or date.min,
    }
    sort_key = sort_key_map.get(sort_by, sort_key_map["updated_at"])
    kept.sort(key=sort_key, reverse=(sort_order == "desc"))

    total = len(kept)
    offset = (page - 1) * page_size
    page_slice = kept[offset : offset + page_size]

    grouped: list[StandardGrouped] = []
    for _key, primary, versions in page_slice:
        grouped.append(
            StandardGrouped(
                **StandardListItem.model_validate(primary).model_dump(),
                base_reference=primary.base_reference,
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


async def get_standard(standard_id: uuid.UUID, db: AsyncSession) -> Standard:
    """Fetch a single standard by UUID. Raises NotFoundError if missing."""
    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")
    return standard


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

