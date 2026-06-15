"""
ORM model: refresh_tokens table.

Not in the original PRD schema but required by the auth design:
"opaque 256-bit token stored hashed in DB" (PRD §13.1).

Storing in DB (vs Redis) allows querying all active sessions for a user —
needed when an admin deactivates a user and must immediately invalidate
all their sessions via:
  UPDATE refresh_tokens SET is_revoked=TRUE WHERE user_id=?

Schema:
  id          UUID        PK
  user_id     UUID        FK users.id NOT NULL
  token_hash  CHAR(64)    NOT NULL UNIQUE  (SHA-256 hex of the raw token)
  expires_at  TIMESTAMPTZ NOT NULL
  is_revoked  BOOLEAN     DEFAULT FALSE
  created_at  TIMESTAMPTZ DEFAULT now()
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class RefreshToken(AsyncBase):
    __tablename__ = "refresh_tokens"

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
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"
