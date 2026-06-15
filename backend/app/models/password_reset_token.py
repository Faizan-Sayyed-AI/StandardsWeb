"""
ORM model: password_reset_tokens table.

Stores single-use, time-limited password reset tokens.
Per PRD §13.1: "32-byte random, hashed in DB, single-use, 1-hour TTL."

Schema:
  id          UUID        PK
  user_id     UUID        FK users.id NOT NULL
  token_hash  CHAR(64)    NOT NULL UNIQUE  (SHA-256 hex of the raw token)
  expires_at  TIMESTAMPTZ NOT NULL
  is_used     BOOLEAN     DEFAULT FALSE    (single-use flag)
  created_at  TIMESTAMPTZ DEFAULT now()
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class PasswordResetToken(AsyncBase):
    __tablename__ = "password_reset_tokens"

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
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PasswordResetToken id={self.id} user_id={self.user_id} used={self.is_used}>"
