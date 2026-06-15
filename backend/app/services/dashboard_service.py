"""
Dashboard stats service (M3).

Returns aggregate counts used by the dashboard summary cards.
All queries run in a single DB round-trip using coroutine concurrency.
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.rss_feed import RssFeed
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import StandardHistory
from app.schemas.dashboard import DashboardStats

log = structlog.get_logger(__name__)


async def get_dashboard_stats(user_id: uuid.UUID, db: AsyncSession) -> DashboardStats:
    """
    Aggregate dashboard statistics for the given authenticated user.

    Queries run sequentially (all are fast indexed count queries).
    """
    # Total standards
    total_standards_r = await db.execute(select(func.count(Standard.id)))
    total_standards: int = total_standards_r.scalar_one()

    # Active standards
    active_r = await db.execute(
        select(func.count(Standard.id)).where(Standard.status == StandardStatus.active)
    )
    active_standards: int = active_r.scalar_one()

    # Purchased standards
    purchased_r = await db.execute(
        select(func.count(Standard.id)).where(Standard.is_purchased == True)  # noqa: E712
    )
    purchased_standards: int = purchased_r.scalar_one()

    # Total feeds
    total_feeds_r = await db.execute(select(func.count(RssFeed.id)))
    total_feeds: int = total_feeds_r.scalar_one()

    # Enabled feeds
    enabled_feeds_r = await db.execute(
        select(func.count(RssFeed.id)).where(RssFeed.is_enabled == True)  # noqa: E712
    )
    enabled_feeds: int = enabled_feeds_r.scalar_one()

    # Events in last 7 days
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    events_r = await db.execute(
        select(func.count(StandardHistory.id)).where(
            StandardHistory.created_at >= seven_days_ago
        )
    )
    events_last_7_days: int = events_r.scalar_one()

    # Unread notifications for current user
    unread_r = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    unread_notifications: int = unread_r.scalar_one()

    return DashboardStats(
        total_standards=total_standards,
        active_standards=active_standards,
        purchased_standards=purchased_standards,
        total_feeds=total_feeds,
        enabled_feeds=enabled_feeds,
        events_last_7_days=events_last_7_days,
        unread_notifications=unread_notifications,
    )
