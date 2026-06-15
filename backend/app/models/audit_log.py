"""
ORM model: audit_logs table (append-only).

Schema (PRD §6.2):
  id             BIGSERIAL  PK  (sequential — gaps indicate tampering)
  actor_id       UUID       FK users.id NULLABLE (null = system action)
  action         VARCHAR(100) NOT NULL  (e.g. "standard.purchased", "feed.created")
  resource_type  VARCHAR(100) NOT NULL  (table / entity name)
  resource_id    UUID       NULLABLE   (PK of affected row)
  payload        JSONB      NULLABLE   (diff or context data)
  ip_address     INET       NULLABLE   (client IP)
  created_at     TIMESTAMPTZ DEFAULT now()  (immutable — never updatable)

Application DB role has INSERT-only permission on this table (enforced in prod).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class AuditLog(AsyncBase):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} actor_id={self.actor_id}>"
