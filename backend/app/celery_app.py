"""
Celery application instance.

The same Docker image is used for the API, worker, and beat services.
The active role is determined by the CMD in docker-compose.yml.

Queues:
  feeds         — RSS polling tasks
  notifications — Email + in-app notification tasks
  maintenance   — Cleanup and health-check tasks
  documents     — AI document-tagging tasks

Beat scheduler: celery_sqlalchemy_scheduler.DatabaseScheduler
  Reads schedules from the celery_schedules table (our custom table) and
  the package's own internal tables (PeriodicTask, CrontabSchedule, etc.).
"""

from celery import Celery

from app.config import settings

# MUST run before Beat's DatabaseScheduler (or any ORM write to the scheduler
# tables): replaces celery-sqlalchemy-scheduler's SQLAlchemy-1.x-only mapper
# listeners, which otherwise crash-loop the beat process. See module docstring.
import app.core.celery_scheduler_compat  # noqa: F401  isort: skip

# ── Application instance ──────────────────────────────────────────────────────
celery: Celery = Celery("ists")

celery.conf.update(
    # Broker & result backend
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,

    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Time
    timezone="UTC",
    enable_utc=True,

    # Ack on receipt (Celery default). Deliberately NOT acks_late, a considered
    # tradeoff: broker redelivery does not increment task retries, so with
    # acks_late a task that hard-crashes the worker (OOM/SIGKILL on a large
    # document) would redeliver and crash it in an endless loop, and
    # partially-sent notification tasks would re-email recipients.
    #
    # The cost of this choice: a task in flight when the worker is *hard*-killed
    # (OOM, SIGKILL, segfault — anything that does not raise a catchable Python
    # exception) is dropped with no redelivery and no retry. Its document stays
    # in 'pending' tag status until someone re-tags it from the UI; there is no
    # automatic reaper. Recovery from caught exceptions is still handled by each
    # task's own self.retry().
    task_acks_late=False,

    # Fair dispatch — workers pull one task at a time
    worker_prefetch_multiplier=1,

    # Result TTL — keep task results for 1 hour then discard
    result_expires=3600,

    # Beat scheduler — reads schedule from PostgreSQL via celery-sqlalchemy-scheduler
    beat_scheduler="celery_sqlalchemy_scheduler.schedulers:DatabaseScheduler",
    beat_max_loop_interval=300,   # re-read schedule every 5 minutes
    beat_sync_every=1,
    beat_dburi=settings.DATABASE_SYNC_URL,  # sync psycopg2 URL for Beat

    # Static periodic tasks
    beat_schedule={
        "refresh-worker-heartbeat-60s": {
            "task": "app.tasks.maintenance.refresh_worker_heartbeat",
            "schedule": 60.0,
            "options": {"queue": "maintenance"},
        }
    },

    # Queue routing
    task_routes={
        "app.tasks.feeds.*": {"queue": "feeds"},
        "app.tasks.notifications.*": {"queue": "notifications"},
        "app.tasks.maintenance.*": {"queue": "maintenance"},
        "app.tasks.documents.*": {"queue": "documents"},
    },

    # Default queue for unrouted tasks
    task_default_queue="feeds",
)

# NOTE: autodiscover_tasks alone does not reliably register every task
# module with this worker in practice — see app/tasks/__init__.py, which
# is the actual source of truth: every task module must be imported there.
celery.autodiscover_tasks(["app.tasks"])
