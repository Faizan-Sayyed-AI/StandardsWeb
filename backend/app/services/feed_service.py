"""
Feed management service (M2).

Handles RSS feed CRUD operations, celery_schedules metadata management,
and manual poll dispatching via Celery.

All mutating operations write an audit log entry.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.celery_schedule import CelerySchedule
from app.models.rss_feed import RssFeed, ScheduleType
from app.schemas.feed import FeedCreate, FeedUpdate
from app.services.audit_service import write_audit_log

log = structlog.get_logger(__name__)


# ── Schedule helpers ──────────────────────────────────────────────────────────
def _cron_from_schedule(
    schedule_type: ScheduleType,
    schedule_hour: int,
    schedule_day_of_week: int | None,
) -> str:
    """
    Build a standard 5-field cron expression from feed schedule settings.

    Examples:
      daily   at 06:00 UTC → "0 6 * * *"
      weekly  on Mon 06:00 → "0 6 * * 0"
    """
    if schedule_type == ScheduleType.daily:
        return f"0 {schedule_hour} * * *"
    # weekly
    dow = schedule_day_of_week if schedule_day_of_week is not None else 0
    return f"0 {schedule_hour} * * {dow}"


async def _upsert_celery_schedule(feed: RssFeed, db: AsyncSession) -> None:
    """Create or update the celery_schedules metadata row for a feed."""
    cron = _cron_from_schedule(feed.schedule_type, feed.schedule_hour, feed.schedule_day_of_week)

    result = await db.execute(
        select(CelerySchedule).where(CelerySchedule.feed_id == feed.id)
    )
    schedule = result.scalar_one_or_none()

    if schedule is None:
        schedule = CelerySchedule(
            task_name="app.tasks.feeds.poll_feed",
            feed_id=feed.id,
            cron_expression=cron,
            is_enabled=feed.is_enabled,
        )
        db.add(schedule)
    else:
        schedule.cron_expression = cron
        schedule.is_enabled = feed.is_enabled


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def list_feeds(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RssFeed], int]:
    """Return a paginated list of all RSS feeds and the total count."""
    offset = (page - 1) * page_size

    count_result = await db.execute(select(func.count(RssFeed.id)))
    total: int = count_result.scalar_one()

    result = await db.execute(
        select(RssFeed).order_by(RssFeed.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_feed(feed_id: uuid.UUID, db: AsyncSession) -> RssFeed:
    """Fetch a single RSS feed by UUID. Raises NotFoundError if missing."""
    feed = await db.get(RssFeed, feed_id)
    if feed is None:
        raise NotFoundError("Feed")
    return feed


async def create_feed(
    payload: FeedCreate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> RssFeed:
    """
    Create a new RSS feed and its celery_schedules metadata row.

    Raises ConflictError if the feed URL already exists.
    """
    # Uniqueness check on URL
    existing = await db.execute(select(RssFeed).where(RssFeed.url == payload.url))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"A feed with URL '{payload.url}' already exists")

    feed = RssFeed(
        name=payload.name,
        url=payload.url,
        tc_committee=payload.tc_committee,
        schedule_type=payload.schedule_type,
        schedule_hour=payload.schedule_hour,
        schedule_day_of_week=payload.schedule_day_of_week,
        is_enabled=payload.is_enabled,
        created_by=actor_id,
    )
    db.add(feed)
    await db.flush()  # assign UUID before creating schedule row

    await _upsert_celery_schedule(feed, db)

    await write_audit_log(
        db,
        action="feed.created",
        resource_type="rss_feed",
        actor_id=actor_id,
        resource_id=feed.id,
        payload={"name": feed.name, "url": feed.url, "schedule_type": feed.schedule_type.value},
        ip_address=ip_address,
    )

    log.info("feed_created", feed_id=str(feed.id), name=feed.name, url=feed.url)
    return feed


async def update_feed(
    feed_id: uuid.UUID,
    payload: FeedUpdate,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> RssFeed:
    """
    Partially update a feed (PATCH semantics).

    Updates celery_schedules if any schedule field or is_enabled changes.
    Raises NotFoundError if missing; ConflictError on URL collision.
    """
    feed = await get_feed(feed_id, db)
    changes: dict[str, Any] = {}
    schedule_changed = False

    if payload.name is not None and payload.name != feed.name:
        changes["name"] = {"from": feed.name, "to": payload.name}
        feed.name = payload.name

    if payload.url is not None and payload.url != feed.url:
        existing = await db.execute(select(RssFeed).where(RssFeed.url == payload.url))
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"A feed with URL '{payload.url}' already exists")
        changes["url"] = {"from": feed.url, "to": payload.url}
        feed.url = payload.url

    if payload.tc_committee is not None:
        changes["tc_committee"] = {"from": feed.tc_committee, "to": payload.tc_committee}
        feed.tc_committee = payload.tc_committee

    if payload.schedule_type is not None and payload.schedule_type != feed.schedule_type:
        changes["schedule_type"] = {
            "from": feed.schedule_type.value,
            "to": payload.schedule_type.value,
        }
        feed.schedule_type = payload.schedule_type
        schedule_changed = True

    if payload.schedule_hour is not None and payload.schedule_hour != feed.schedule_hour:
        changes["schedule_hour"] = {"from": feed.schedule_hour, "to": payload.schedule_hour}
        feed.schedule_hour = payload.schedule_hour
        schedule_changed = True

    if payload.schedule_day_of_week is not None:
        changes["schedule_day_of_week"] = {
            "from": feed.schedule_day_of_week,
            "to": payload.schedule_day_of_week,
        }
        feed.schedule_day_of_week = payload.schedule_day_of_week
        schedule_changed = True

    if payload.is_enabled is not None and payload.is_enabled != feed.is_enabled:
        changes["is_enabled"] = {"from": feed.is_enabled, "to": payload.is_enabled}
        feed.is_enabled = payload.is_enabled
        schedule_changed = True

    if changes:
        await db.flush()

        if schedule_changed:
            await _upsert_celery_schedule(feed, db)

        await write_audit_log(
            db,
            action="feed.updated",
            resource_type="rss_feed",
            actor_id=actor_id,
            resource_id=feed.id,
            payload=changes,
            ip_address=ip_address,
        )
        log.info("feed_updated", feed_id=str(feed.id), changes=list(changes.keys()))

    return feed


async def delete_feed(
    feed_id: uuid.UUID,
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Hard-delete an RSS feed (its celery_schedules row cascades via FK).

    Raises NotFoundError if missing.
    """
    feed = await get_feed(feed_id, db)

    await write_audit_log(
        db,
        action="feed.deleted",
        resource_type="rss_feed",
        actor_id=actor_id,
        resource_id=feed.id,
        payload={"name": feed.name, "url": feed.url},
        ip_address=ip_address,
    )

    await db.delete(feed)
    log.info("feed_deleted", feed_id=str(feed_id), name=feed.name)


# ── Manual poll trigger ───────────────────────────────────────────────────────
async def trigger_manual_poll(feed_id: uuid.UUID, db: AsyncSession) -> str:
    """
    Dispatch the poll_feed Celery task immediately (fire-and-forget).

    Returns the Celery task ID string.
    Raises NotFoundError if the feed doesn't exist.
    """
    # Verify feed exists before dispatching
    feed = await get_feed(feed_id, db)

    # Deferred import to break the tasks → services circular import
    from app.tasks.feeds import poll_feed  # noqa: PLC0415

    task = poll_feed.delay(str(feed.id))

    log.info("manual_poll_triggered", feed_id=str(feed_id), task_id=task.id)
    return task.id
