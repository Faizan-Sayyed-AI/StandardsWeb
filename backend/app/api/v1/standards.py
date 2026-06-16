"""
Standards router — /api/v1/standards/*

Read-only endpoints for M3 UI. Write operations (purchase, status update)
are added in M4/M6.

Endpoints:
  GET /standards           — Filtered/sorted/paginated list (viewer+)
  GET /standards/{id}      — Standard detail (viewer+)
  GET /standards/{id}/history — Change history timeline (viewer+)
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.models.standard import StandardStatus
from app.schemas.pagination import Page
from app.schemas.standard import StandardDetail, StandardHistoryItem, StandardListItem
from app.services import standard_service

router = APIRouter(prefix="/standards", tags=["Standards"])


@router.get(
    "",
    response_model=Page[StandardListItem],
    summary="List standards — filterable, sortable, paginated (viewer+)",
)
async def list_standards(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Search iso_reference, title, committee"),
    status: StandardStatus | None = Query(default=None),
    tc_committee: str | None = Query(default=None),
    is_purchased: bool | None = Query(default=None),
    sort_by: Literal["iso_reference", "title", "updated_at", "status", "created_at"] = Query(
        default="updated_at"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> Page[StandardListItem]:
    standards, total = await standard_service.list_standards(
        db,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        tc_committee=tc_committee,
        is_purchased=is_purchased,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return Page[StandardListItem](
        items=[StandardListItem.model_validate(s) for s in standards],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{standard_id}",
    response_model=StandardDetail,
    summary="Standard detail (viewer+)",
)
async def get_standard(
    standard_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
) -> StandardDetail:
    """Fetch a single standard's full detail. Returns 404 if not found."""
    standard = await standard_service.get_standard(standard_id, db)
    return StandardDetail.model_validate(standard)


@router.get(
    "/{standard_id}/history",
    response_model=Page[StandardHistoryItem],
    summary="Standard change history (viewer+)",
)
async def get_standard_history(
    standard_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[StandardHistoryItem]:
    """
    Return the paginated change history timeline for a standard (newest first).
    Returns 404 if the standard doesn't exist.
    """
    history, total = await standard_service.get_standard_history(
        standard_id, db, page=page, page_size=page_size
    )
    return Page[StandardHistoryItem](
        items=[StandardHistoryItem.model_validate(h) for h in history],
        total=total,
        page=page,
        page_size=page_size,
    )


from pydantic import BaseModel

class StandardPurchaseRequest(BaseModel):
    purchase_notes: str | None = None


from app.api.deps import ManagerOrAdminUser

@router.post(
    "/{standard_id}/purchase",
    response_model=StandardDetail,
    summary="Mark standard as purchased (manager+)",
)
async def purchase_standard(
    standard_id: uuid.UUID,
    payload: StandardPurchaseRequest,
    db: DBSession,
    current_user: ManagerOrAdminUser,
) -> StandardDetail:
    """Mark standard as purchased. Triggers notifications and logs audit."""
    standard = await standard_service.purchase_standard(
        standard_id=standard_id,
        actor_id=current_user.id,
        purchase_notes=payload.purchase_notes,
        db=db,
    )

    await db.commit()

    # Trigger bulk notifications (in-app notifications for all users + email mapped lists)
    from app.tasks.notifications import send_bulk_notification
    send_bulk_notification.delay({
        "event_type": "purchased",
        "standard_id": str(standard.id),
        "triggered_by_id": str(current_user.id),
    })

    return StandardDetail.model_validate(standard)

