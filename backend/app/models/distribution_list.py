"""
ORM models: distribution_lists and distribution_list_members tables.

Schema (PRD §6.2):
  distribution_lists:
    id           UUID        PK
    name         VARCHAR(255) UNIQUE NOT NULL
    description  TEXT        NULLABLE
    created_by   UUID        FK users.id
    created_at   TIMESTAMPTZ DEFAULT now()

  distribution_list_members:
    id        UUID        PK
    list_id   UUID        FK distribution_lists.id
    email     VARCHAR(255) NOT NULL
    name      VARCHAR(255) NULLABLE
    is_active BOOLEAN     DEFAULT TRUE
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class DistributionList(AsyncBase):
    __tablename__ = "distribution_lists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DistributionList id={self.id} name={self.name}>"


class DistributionListMember(AsyncBase):
    __tablename__ = "distribution_list_members"
    __table_args__ = (
        UniqueConstraint("list_id", "email", name="uq_list_member_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("distribution_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    def __repr__(self) -> str:
        return f"<DistributionListMember list_id={self.list_id} email={self.email}>"
