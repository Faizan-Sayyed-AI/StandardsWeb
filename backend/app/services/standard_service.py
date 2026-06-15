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
