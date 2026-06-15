"""
Celery tasks: maintenance queue.

Tasks:
  cleanup_old_notifications()   — Archive in-app notifications older than 90 days (daily 02:00 UTC)
  refresh_worker_heartbeat()    — Update worker health record (every 60 seconds)
"""

import structlog

from app.celery_app import celery

log = structlog.get_logger(__name__)


@celery.task(name="app.tasks.maintenance.cleanup_old_notifications", queue="maintenance")
def cleanup_old_notifications() -> dict:  # type: ignore[no-untyped-def]
    """Archive in-app notifications older than 90 days. M6."""
    log.info("cleanup_old_notifications_stub_called")
    return {"status": "stub"}


@celery.task(name="app.tasks.maintenance.refresh_worker_heartbeat", queue="maintenance")
def refresh_worker_heartbeat() -> dict:  # type: ignore[no-untyped-def]
    """Write a heartbeat timestamp to the worker health store. M6."""
    log.info("refresh_worker_heartbeat_stub_called")
    return {"status": "stub"}
