"""
Celery tasks: feeds queue.

M2 will implement the full RSS polling logic here.
Stubs are importable so the worker container starts without errors.

Tasks:
  poll_feed(feed_id)    — Fetch, parse, and diff a single RSS feed
  poll_all_feeds()      — Fan-out: dispatch poll_feed for all enabled feeds
"""

import structlog

from app.celery_app import celery

log = structlog.get_logger(__name__)


@celery.task(
    name="app.tasks.feeds.poll_feed",
    queue="feeds",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def poll_feed(self, feed_id: str) -> dict:  # type: ignore[no-untyped-def]
    """
    Fetch a single RSS feed, parse entries, diff against DB, write history.
    Full implementation in M2.
    """
    log.info("poll_feed_stub_called", feed_id=feed_id)
    return {"status": "stub", "feed_id": feed_id}


@celery.task(name="app.tasks.feeds.poll_all_feeds", queue="feeds")
def poll_all_feeds() -> dict:  # type: ignore[no-untyped-def]
    """Fan-out: iterate enabled feeds and dispatch poll_feed for each. M2."""
    log.info("poll_all_feeds_stub_called")
    return {"status": "stub"}
