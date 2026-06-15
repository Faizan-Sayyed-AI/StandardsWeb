"""
ORM model: celery_schedules table.

Our custom schedule-tracking table used by the admin API to manage
per-feed Celery Beat schedules. This is separate from celery-sqlalchemy-scheduler's
own internal tables (PeriodicTask, CrontabSchedule, etc.).

Schema (PRD §6.2):
  id               INTEGER  PK SERIAL
  task_name        VARCHAR(255) NOT NULL
  feed_id          UUID     FK rss_feeds.id NULLABLE
  cron_expression  VARCHAR(100) NOT NULL
  is_enabled       BOOLEAN  DEFAULT TRUE
  last_run_at      TIMESTAMPTZ NULLABLE
  next_run_at      TIMESTAMPTZ NULLABLE
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from app.database import AsyncBase


class CelerySchedule(AsyncBase):
    __tablename__ = "celery_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rss_feeds.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<CelerySchedule id={self.id} task_name={self.task_name}>"
