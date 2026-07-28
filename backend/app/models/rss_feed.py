"""
ORM model: rss_feeds table.

Schema (PRD §6.2):
  id                    UUID        PK
  name                  VARCHAR(255) NOT NULL
  url                   TEXT        UNIQUE NOT NULL
  tc_committee          VARCHAR(100) NULLABLE
  schedule_type         ENUM(daily|weekly) NOT NULL
  schedule_hour         SMALLINT    0-23
  schedule_day_of_week  SMALLINT    NULLABLE 0-6 (0=Mon)
  is_enabled            BOOLEAN     DEFAULT TRUE
  last_polled_at        TIMESTAMPTZ NULLABLE
  last_poll_status      ENUM(pending|ok|failed) DEFAULT pending
  failure_count         SMALLINT    DEFAULT 0
  created_by            UUID        FK users.id
  api_key_id            UUID        FK api_keys.id NULLABLE
  created_at            TIMESTAMPTZ DEFAULT now()
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class ScheduleType(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"


class PollStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    failed = "failed"


class RssFeed(AsyncBase):
    __tablename__ = "rss_feeds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    tc_committee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schedule_type: Mapped[ScheduleType] = mapped_column(
        Enum(ScheduleType, name="schedule_type_enum", create_type=False),
        nullable=False,
        server_default=ScheduleType.daily.value,
    )
    schedule_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="6")
    schedule_day_of_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_poll_status: Mapped[PollStatus] = mapped_column(
        Enum(PollStatus, name="poll_status_enum", create_type=False),
        nullable=False,
        server_default=PollStatus.pending.value,
    )
    failure_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Nullable at the DB level for existing rows created before this column
    # existed (see scripts/backfill_api_keys.py) — application code always
    # assigns one on create. RESTRICT so an api_keys row with feeds still
    # attached can't be deleted out from under them; see api_key_service.
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RssFeed id={self.id} name={self.name}>"
