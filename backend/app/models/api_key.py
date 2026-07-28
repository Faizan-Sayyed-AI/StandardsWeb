"""
ORM model: api_keys table.

Holds the pool of rss2json.com API keys that rss_feeds rows are distributed
across (each key is limited to a fixed number of feeds — see `capacity`).

Schema:
  id                    UUID        PK
  label                 VARCHAR(255) UNIQUE NOT NULL
  key_value             TEXT        NOT NULL  (Fernet-encrypted, see app/core/crypto.py)
  capacity              SMALLINT    DEFAULT 25
  status                ENUM(active|rate_limited|expired|disabled) DEFAULT active
  consecutive_failures  SMALLINT    DEFAULT 0
  last_used_at          TIMESTAMPTZ NULLABLE
  last_failure_at       TIMESTAMPTZ NULLABLE
  notes                 TEXT        NULLABLE
  created_at            TIMESTAMPTZ DEFAULT now()
  updated_at            TIMESTAMPTZ DEFAULT now()
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class ApiKeyStatus(str, enum.Enum):
    active = "active"
    rate_limited = "rate_limited"
    expired = "expired"
    disabled = "disabled"


class ApiKey(AsyncBase):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    label: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    key_value: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="25")
    status: Mapped[ApiKeyStatus] = mapped_column(
        Enum(ApiKeyStatus, name="api_key_status_enum", create_type=False),
        nullable=False,
        server_default=ApiKeyStatus.active.value,
    )
    consecutive_failures: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} label={self.label} status={self.status}>"
