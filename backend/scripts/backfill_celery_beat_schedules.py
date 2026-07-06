"""
One-time backfill script: materialize existing celery_schedules rows into
celery_sqlalchemy_scheduler's own PeriodicTask/CrontabSchedule tables.

Needed because feeds created before the celery_beat_sync.py fix have a
celery_schedules metadata row but no corresponding PeriodicTask — so Beat
never dispatches them automatically.

Run after deploying the fix:
  docker compose exec web python scripts/backfill_celery_beat_schedules.py
"""

import asyncio
import sys

import structlog
from sqlalchemy import select

# Ensure the app package is importable when run from /app inside the container
sys.path.insert(0, "/app")

from app.core.logging import setup_logging
from app.database import async_session_factory
from app.models.celery_schedule import CelerySchedule
from app.services import celery_beat_sync

setup_logging()
log = structlog.get_logger(__name__)


async def backfill() -> None:
    log.info("backfill_celery_beat_schedules_starting")

    async with async_session_factory() as session:
        result = await session.execute(select(CelerySchedule))
        schedules = result.scalars().all()

        for s in schedules:
            if s.feed_id is None:
                continue
            await asyncio.to_thread(
                celery_beat_sync.sync_feed_schedule,
                str(s.feed_id),
                s.cron_expression,
                s.is_enabled,
            )

        print(f"Backfilled {len(schedules)} celery beat schedules")


if __name__ == "__main__":
    asyncio.run(backfill())
