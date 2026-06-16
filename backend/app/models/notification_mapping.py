"""
ORM model: notification_trigger_mappings table.

Schema (PRD §6.2):
  id               UUID   PK
  event_type       ENUM   NOT NULL  (same enum as standard_history.event_type)
  list_id          UUID   FK distribution_lists.id
  notify_all_users BOOLEAN DEFAULT FALSE
"""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class NotificationTriggerMapping(AsyncBase):
    __tablename__ = "notification_trigger_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "new", "updated", "amended", "withdrawn", "replaced", "purchased", "status_change", "document_uploaded",
            name="event_type_enum",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("distribution_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    notify_all_users: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationTriggerMapping event_type={self.event_type} list_id={self.list_id}>"
        )

