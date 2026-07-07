"""
Celery tasks package.

Despite celery_app.py calling celery.autodiscover_tasks(["app.tasks"]),
that alone does NOT register new task modules with this worker — confirmed
live (a new task module's Celery task was absent from the worker's [tasks]
startup banner until explicitly imported here). Every task module must be
imported below, or it will silently never run.
"""

from app.tasks.feeds import poll_feed, poll_all_feeds
from app.tasks.notifications import send_email_notification, send_bulk_notification
from app.tasks.maintenance import cleanup_old_notifications, refresh_worker_heartbeat
from app.tasks.documents import tag_document
