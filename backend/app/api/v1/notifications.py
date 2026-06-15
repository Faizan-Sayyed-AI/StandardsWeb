"""
Notifications router — /api/v1/notifications/*

Endpoints:
  GET  /notifications              — Paginated list for current user (viewer+)
  GET  /notifications/count        — Unread count only (used by bell polling)
  PATCH /notifications/{id}/read   — Mark single notification read (viewer+)
  POST /notifications/mark-all-read — Mark all unread as read (viewer+)
"""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.notification import NotificationCountResponse, NotificationResponse
from app.schemas.pagination import Page
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "/count",
    response_model=NotificationCountResponse,
    summary="Unread notification count for current user (viewer+)",
)
async def get_unread_count(db: DBSession, current_user: CurrentUser) -> NotificationCountResponse:
    """
    Lightweight endpoint for the bell-icon polling (every 30 s from the frontend).
    Returns only the unread count — no notification data.
    """
    count = await notification_service.get_unread_count(current_user.id, db)
    return NotificationCountResponse(unread=count)


@router.get(
    "",
    response_model=Page[NotificationResponse],
    summary="List notifications for current user (viewer+)",
)
async def list_notifications(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False, description="Return only unread notifications"),
) -> Page[NotificationResponse]:
    notifications, total = await notification_service.list_notifications(
        current_user.id, db, page=page, page_size=page_size, unread_only=unread_only
    )
    return Page[NotificationResponse](
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark a single notification as read (viewer+)",
)
async def mark_read(
    notification_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> NotificationResponse:
    """Mark a notification as read. Returns 403 if it belongs to another user."""
    notification = await notification_service.mark_notification_read(
        notification_id, current_user.id, db
    )
    return NotificationResponse.model_validate(notification)


@router.post(
    "/mark-all-read",
    summary="Mark all notifications as read for current user (viewer+)",
)
async def mark_all_read(db: DBSession, current_user: CurrentUser) -> dict:
    """Mark all unread notifications for the authenticated user as read."""
    count = await notification_service.mark_all_read(current_user.id, db)
    return {"marked": count}
