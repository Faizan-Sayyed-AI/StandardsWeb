"""
Celery application instance.

The same Docker image is used for the API, worker, and beat services.
The active role is determined by the CMD in docker-compose.yml.

Queues:
  feeds         — RSS polling tasks
  notifications — Email + in-app notification tasks
  maintenance   — Cleanup and health-check tasks

Beat scheduler: celery_sqlalchemy_scheduler.DatabaseScheduler
  Reads schedules from the celery_schedules table (our custom table) and
  the package's own internal tables (PeriodicTask, CrontabSchedule, etc.).
"""

from celery import Celery

from app.config import settings

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

    # Reliability — re-queue tasks if a worker crashes mid-execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,

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
    },

    # Default queue for unrouted tasks
    task_default_queue="feeds",
)

# Auto-discover tasks in app/tasks/*.py
celery.autodiscover_tasks(["app.tasks"])
