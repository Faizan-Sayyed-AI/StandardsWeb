"""
ORM model: standard_history table (append-only).

Schema (PRD §6.2):
  id           UUID   PK
  standard_id  UUID   FK standards.id NOT NULL
  event_type   ENUM(new|updated|amended|withdrawn|replaced|purchased|status_change) NOT NULL
  old_value    JSONB  NULLABLE
  new_value    JSONB  NOT NULL
  source       ENUM(rss|manual|system) NOT NULL
  triggered_by UUID   FK users.id NULLABLE
  notes        TEXT   NULLABLE
  created_at   TIMESTAMPTZ DEFAULT now()

No rows are ever deleted from this table.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class EventType(str, enum.Enum):
    new = "new"
    updated = "updated"
    amended = "amended"
    withdrawn = "withdrawn"
    replaced = "replaced"
    purchased = "purchased"
    status_change = "status_change"


class EventSource(str, enum.Enum):
    rss = "rss"
    manual = "manual"
    system = "system"


class StandardHistory(AsyncBase):
    __tablename__ = "standard_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    standard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("standards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type_enum", create_type=False),
        nullable=False,
    )
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource, name="event_source_enum", create_type=False),
        nullable=False,
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<StandardHistory id={self.id} event_type={self.event_type}>"
