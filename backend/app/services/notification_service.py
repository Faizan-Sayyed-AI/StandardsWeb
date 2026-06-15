"""
Notification service (M3).

Provides read and mark-read operations for the authenticated user's
in-app notifications. Write (create) operations are performed by the
notification Celery tasks in M5.
"""

import uuid

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.notification import Notification

log = structlog.get_logger(__name__)


async def list_notifications(
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> tuple[list[Notification], int]:
    """Return paginated notifications for the given user (newest first)."""
    query = select(Notification).where(Notification.user_id == user_id)

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            *([Notification.is_read == False] if unread_only else []),  # noqa: E712
        )
    )
    total: int = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_unread_count(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Return the count of unread notifications for the given user."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return result.scalar_one()


async def mark_notification_read(
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Notification:
    """
    Mark a single notification as read.
    Raises NotFoundError if missing; ForbiddenError if it belongs to another user.
    """
    notification = await db.get(Notification, notification_id)
    if notification is None:
        raise NotFoundError("Notification")
    if notification.user_id != user_id:
        raise ForbiddenError("This notification belongs to another user")

    notification.is_read = True
    await db.flush()
    return notification


async def mark_all_read(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Mark all unread notifications for the user as read. Returns count marked."""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
        .returning(Notification.id)
    )
    marked = len(result.all())
    log.info("notifications_marked_all_read", user_id=str(user_id), count=marked)
    return marked
