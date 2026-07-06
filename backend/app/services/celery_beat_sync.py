"""
Materializes per-feed cron schedules into celery_sqlalchemy_scheduler's own
tables (celery_crontab_schedule, celery_periodic_task) — the tables Celery
Beat's DatabaseScheduler actually reads.

`celery_schedules` (app.models.celery_schedule.CelerySchedule) is admin-facing
metadata only; Beat never reads it (see AUTOMATION.md §1 "Known gap"). This
module is the missing bridge between the two.

Writes go through SQLAlchemy Core against the package's own Table objects
(imported from its ORM classes, so the schema always matches the pinned
celery-sqlalchemy-scheduler version) rather than through an ORM Session.
This is deliberate, not a style choice: the package's PeriodicTaskChanged
mapper event listeners (models.py `after_insert`/`after_update` on
PeriodicTask/CrontabSchedule) use SQLAlchemy 1.x's removed `select([Model])`
list syntax and raise ArgumentError under SQLAlchemy 2.0 (confirmed
empirically — any ORM-level insert/update to these tables crashes,
including Beat's own default `beat_schedule` entries, which is the
'Cannot add entry ...' error already seen in the beat container log).
Core-level statements never touch the ORM unit-of-work, so those mapper
events never fire — which means we must bump `celery_periodic_task_changed`
ourselves (`_touch_changed`) to signal a running Beat process to reload,
since we can't rely on the package's own (broken) listener to do it.

These are legacy sync SQLAlchemy tables (bound to DATABASE_SYNC_URL, the
same URI Beat itself uses as `beat_dburi`), so callers running in async
context must wrap calls via `asyncio.to_thread(...)`.
"""

import datetime as dt
import json

from celery_sqlalchemy_scheduler.models import CrontabSchedule, PeriodicTask, PeriodicTaskChanged
from celery_sqlalchemy_scheduler.session import ModelBase
from sqlalchemy import and_, create_engine, delete, insert, select, update

from app.config import settings

_engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
ModelBase.metadata.create_all(_engine)

_crontab_table = CrontabSchedule.__table__
_periodic_task_table = PeriodicTask.__table__
_changed_table = PeriodicTaskChanged.__table__

_TASK_NAME = "app.tasks.feeds.poll_feed"


def _periodic_task_name(feed_id: str) -> str:
    return f"feed-poll-{feed_id}"


def _cron_fields(cron_expression: str) -> dict:
    """Split a standard 5-field cron string into celery_sqlalchemy_scheduler's field names."""
    minute, hour, day_of_month, month_of_year, day_of_week = cron_expression.split()
    return {
        "minute": minute,
        "hour": hour,
        "day_of_month": day_of_month,
        "month_of_year": month_of_year,
        "day_of_week": day_of_week,
    }


def _touch_changed(conn) -> None:
    """Bump celery_periodic_task_changed so a running Beat process re-reads the schedule."""
    now = dt.datetime.now(dt.timezone.utc)
    row = conn.execute(select(_changed_table.c.id).where(_changed_table.c.id == 1)).first()
    if row is None:
        conn.execute(insert(_changed_table).values(id=1, last_update=now))
    else:
        conn.execute(update(_changed_table).where(_changed_table.c.id == 1).values(last_update=now))


def sync_feed_schedule(feed_id: str, cron_expression: str, is_enabled: bool) -> None:
    """Create or update the Beat PeriodicTask entry for one feed."""
    fields = _cron_fields(cron_expression)
    with _engine.begin() as conn:
        crontab_row = conn.execute(
            select(_crontab_table.c.id).where(
                and_(_crontab_table.c.timezone == "UTC", *(
                    _crontab_table.c[k] == v for k, v in fields.items()
                ))
            )
        ).first()
        if crontab_row is None:
            crontab_id = conn.execute(
                insert(_crontab_table).values(timezone="UTC", **fields)
            ).inserted_primary_key[0]
        else:
            crontab_id = crontab_row.id

        name = _periodic_task_name(feed_id)
        task_row = conn.execute(
            select(_periodic_task_table.c.id).where(_periodic_task_table.c.name == name)
        ).first()
        if task_row is None:
            conn.execute(
                insert(_periodic_task_table).values(
                    name=name,
                    task=_TASK_NAME,
                    crontab_id=crontab_id,
                    args=json.dumps([feed_id]),
                    kwargs="{}",
                    enabled=is_enabled,
                    total_run_count=0,
                )
            )
        else:
            conn.execute(
                update(_periodic_task_table)
                .where(_periodic_task_table.c.id == task_row.id)
                .values(crontab_id=crontab_id, enabled=is_enabled)
            )

        _touch_changed(conn)


def delete_feed_schedule(feed_id: str) -> None:
    """Remove the Beat PeriodicTask entry for a deleted feed."""
    name = _periodic_task_name(feed_id)
    with _engine.begin() as conn:
        result = conn.execute(delete(_periodic_task_table).where(_periodic_task_table.c.name == name))
        if result.rowcount:
            _touch_changed(conn)
