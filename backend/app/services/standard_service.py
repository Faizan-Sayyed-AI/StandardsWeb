"""
Standards read service (M3).

All endpoints are read-only in M3. Write operations (purchase, status change)
are added in M4/M6. Supports filtered, sorted, paginated list queries.
"""

import uuid
from typing import Literal

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import StandardHistory

log = structlog.get_logger(__name__)


async def list_standards(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: StandardStatus | None = None,
    tc_committee: str | None = None,
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
            )
        )
    if status is not None:
        conditions.append(Standard.status == status)
    if tc_committee is not None:
        conditions.append(Standard.tc_committee == tc_committee)
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


async def get_standard(standard_id: uuid.UUID, db: AsyncSession) -> Standard:
    """Fetch a single standard by UUID. Raises NotFoundError if missing."""
    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")
    return standard


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
) -> Standard:
    """
    Mark standard as purchased, append standard history row, write audit log.
    """
    import datetime
    from app.models.standard_history import EventSource, EventType, StandardHistory
    from app.services.audit_service import write_audit_log

    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")

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
    return standard

