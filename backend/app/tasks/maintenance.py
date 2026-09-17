"""
Celery tasks: maintenance queue.

Tasks:
  cleanup_old_notifications()      — Archive in-app notifications older than 90 days (daily 02:00 UTC)
  refresh_worker_heartbeat()       — Update worker health record (every 60 seconds)
  recover_rate_limited_api_keys()  — Return rate-limited keys to the pool (hourly)
"""

import asyncio
import redis
from datetime import datetime, timedelta, timezone
import structlog

from app.celery_app import celery
from app.config import settings

log = structlog.get_logger(__name__)


@celery.task(name="app.tasks.maintenance.cleanup_old_notifications", queue="maintenance")
def cleanup_old_notifications() -> dict:  # type: ignore[no-untyped-def]
    """Archive in-app notifications older than 90 days. M6."""
    log.info("cleanup_old_notifications_stub_called")
    return {"status": "stub"}


@celery.task(name="app.tasks.maintenance.refresh_worker_heartbeat", queue="maintenance")
def refresh_worker_heartbeat() -> dict:  # type: ignore[no-untyped-def]
    """Write a heartbeat timestamp to the worker health store (Redis)."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        timestamp = datetime.now(timezone.utc).isoformat()
        r.set("worker:heartbeat", timestamp)
        log.info("worker_heartbeat_refreshed", timestamp=timestamp)
        return {"status": "ok", "timestamp": timestamp}
    except Exception as e:
        log.error("failed_to_refresh_worker_heartbeat", error=str(e))
        return {"status": "error", "reason": str(e)}


async def _recover_rate_limited_api_keys_async() -> dict:
    from app.database import async_session_factory
    from app.services.api_key_service import recover_rate_limited_keys

    cooldown = timedelta(hours=settings.API_KEY_RATE_LIMIT_COOLDOWN_HOURS)
    async with async_session_factory() as session:
        recovered = await recover_rate_limited_keys(session, cooldown=cooldown)
        labels = [key.label for key in recovered]
        await session.commit()
    return {"status": "ok", "recovered": len(labels), "labels": labels}


@celery.task(
    name="app.tasks.maintenance.recover_rate_limited_api_keys", queue="maintenance"
)
def recover_rate_limited_api_keys() -> dict:  # type: ignore[no-untyped-def]
    """
    Put rate-limited API keys back into the pool once their cooldown elapses.

    Without this, `rate_limited` is a terminal state: a key in it is never used
    for a request, and a successful request is the only other way out, so the
    pool drains one key at a time and RSS polling stops permanently. That is
    what happened in production — all three keys sat rate-limited for weeks
    while rss2json's own quotas reset daily, and every scheduled poll was
    skipped.

    Runs hourly rather than daily so recovery is prompt: the cooldown, not this
    interval, decides when a key is eligible.
    """
    try:
        return asyncio.run(_recover_rate_limited_api_keys_async())
    except Exception as e:
        log.error("failed_to_recover_rate_limited_api_keys", error=str(e))
        return {"status": "error", "reason": str(e)}

