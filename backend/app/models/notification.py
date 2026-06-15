"""
ORM model: notifications table.

Schema (PRD §6.2):
  id                  UUID        PK
  user_id             UUID        FK users.id NOT NULL
  event_type          ENUM(...)   NOT NULL  (same values as standard_history.event_type)
  severity            ENUM(info|warning|critical) NOT NULL
  title               VARCHAR(255) NOT NULL
  body                TEXT        NOT NULL
  related_standard_id UUID        FK standards.id NULLABLE
  is_read             BOOLEAN     DEFAULT FALSE
  created_at          TIMESTAMPTZ DEFAULT now()
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class NotificationSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class Notification(AsyncBase):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # event_type shares the same ENUM as standard_history
    event_type: Mapped[str] = mapped_column(
        Enum(
            "new", "updated", "amended", "withdrawn", "replaced", "purchased", "status_change",
            name="event_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    severity: Mapped[NotificationSeverity] = mapped_column(
        Enum(NotificationSeverity, name="notification_severity_enum", create_type=False),
        nullable=False,
        server_default=NotificationSeverity.info.value,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_standard_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("standards.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} severity={self.severity}>"
