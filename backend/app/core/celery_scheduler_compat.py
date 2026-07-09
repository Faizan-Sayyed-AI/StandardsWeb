"""
SQLAlchemy 2.0 compatibility patch for celery-sqlalchemy-scheduler 0.3.0.

The package registers mapper event listeners (models.py bottom) whose
implementation uses SQLAlchemy 1.x's removed `select([Model])` list syntax
(models.py:200, PeriodicTaskChanged.update_changed). Under the project's
pinned sqlalchemy==2.0.* this raises ArgumentError on ANY ORM flush that
touches PeriodicTask / CrontabSchedule / IntervalSchedule / SolarSchedule.

That is fatal for Celery Beat, not just noisy: on startup, DatabaseScheduler's
all_as_schedule() backfills NULL last_run_at on each PeriodicTask model
(schedulers.py Entry.__init__), so the session is dirty when the next entry's
`model.schedule` lazy-load autoflushes → the broken listener raises →
Entry.__init__ catches it and calls _disable() → session.commit() on the
poisoned session → PendingRollbackError → Beat process exits → container
restart loop → no scheduled task ever fires.

Simply reassigning the classmethods is not enough: `listen()` captured bound
references at import time. We must event.remove() the original listeners and
re-register fixed ones. SQLAlchemy keys bound-method listeners by
(id(__func__), id(__self__)), so passing fresh bound-method objects to
remove() matches the originals.

Import this module BEFORE Beat or any ORM write to the scheduler tables —
app/celery_app.py imports it at the top, which covers beat, worker, and API
(all of them import celery_app).
"""

import datetime as dt

import sqlalchemy as sa
from celery.utils.log import get_logger
from celery_sqlalchemy_scheduler.models import (
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    PeriodicTaskChanged,
    SolarSchedule,
)
from sqlalchemy import event

logger = get_logger(__name__)

_changed_table = PeriodicTaskChanged.__table__


def _update_changed(mapper, connection, target) -> None:
    """SQLA-2.0 rewrite of PeriodicTaskChanged.update_changed (models.py:194)."""
    now = dt.datetime.now(dt.timezone.utc)
    row = connection.execute(
        sa.select(_changed_table.c.id).where(_changed_table.c.id == 1)
    ).first()
    if row is None:
        connection.execute(sa.insert(_changed_table).values(id=1, last_update=now))
    else:
        connection.execute(
            sa.update(_changed_table).where(_changed_table.c.id == 1).values(last_update=now)
        )


def _changed(mapper, connection, target) -> None:
    """SQLA-2.0 rewrite of PeriodicTaskChanged.changed (models.py:183)."""
    if not target.no_changes:
        _update_changed(mapper, connection, target)


# Mirror of the listen() calls at the bottom of the package's models.py.
_REGISTRATIONS = [
    (PeriodicTask, "after_insert", PeriodicTaskChanged.update_changed, _update_changed),
    (PeriodicTask, "after_delete", PeriodicTaskChanged.update_changed, _update_changed),
    (PeriodicTask, "after_update", PeriodicTaskChanged.changed, _changed),
    (IntervalSchedule, "after_insert", PeriodicTaskChanged.update_changed, _update_changed),
    (IntervalSchedule, "after_delete", PeriodicTaskChanged.update_changed, _update_changed),
    (IntervalSchedule, "after_update", PeriodicTaskChanged.update_changed, _update_changed),
    (CrontabSchedule, "after_insert", PeriodicTaskChanged.update_changed, _update_changed),
    (CrontabSchedule, "after_delete", PeriodicTaskChanged.update_changed, _update_changed),
    (CrontabSchedule, "after_update", PeriodicTaskChanged.update_changed, _update_changed),
    (SolarSchedule, "after_insert", PeriodicTaskChanged.update_changed, _update_changed),
    (SolarSchedule, "after_delete", PeriodicTaskChanged.update_changed, _update_changed),
    (SolarSchedule, "after_update", PeriodicTaskChanged.update_changed, _update_changed),
]

_applied = False


def apply() -> None:
    """Swap the package's broken mapper listeners for 2.0-compatible ones. Idempotent."""
    global _applied
    if _applied:
        return
    for target, identifier, original, replacement in _REGISTRATIONS:
        try:
            event.remove(target, identifier, original)
        except sa.exc.InvalidRequestError:
            # Listener not found — package version changed its registrations;
            # still attach ours so the changed-timestamp keeps being bumped.
            logger.warning(
                "celery_scheduler_compat: original %s listener on %s not found",
                identifier,
                target.__name__,
            )
        event.listen(target, identifier, replacement)
    _applied = True
    logger.info("celery_scheduler_compat: patched %d scheduler mapper listeners", len(_REGISTRATIONS))


apply()
