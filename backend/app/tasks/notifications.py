"""
Celery tasks: notifications queue.

M5 will implement full email sending via aiosmtplib.
Stubs are importable so the worker container starts without errors.

Tasks:
  send_email_notification(payload)  — Send transactional email to a distribution list
  send_bulk_notification(payload)   — Broadcast in-app + email to all active users
"""

import structlog

from app.celery_app import celery

log = structlog.get_logger(__name__)


@celery.task(name="app.tasks.notifications.send_email_notification", queue="notifications")
def send_email_notification(payload: dict) -> dict:  # type: ignore[no-untyped-def]
    """Assemble and send an HTML email to a distribution list. M5."""
    log.info("send_email_notification_stub_called", payload=payload)
    return {"status": "stub"}


@celery.task(name="app.tasks.notifications.send_bulk_notification", queue="notifications")
def send_bulk_notification(payload: dict) -> dict:  # type: ignore[no-untyped-def]
    """Send in-app notification to all active users + email to mapped lists. M5."""
    log.info("send_bulk_notification_stub_called", payload=payload)
    return {"status": "stub"}
