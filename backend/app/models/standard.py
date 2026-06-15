"""
ORM model: standards table.

Schema (PRD §6.2):
  id              UUID        PK
  iso_reference   VARCHAR(100) UNIQUE NOT NULL  (e.g. ISO 9001:2015)
  title           TEXT        NOT NULL
  edition         VARCHAR(50) NULLABLE
  tc_committee    VARCHAR(100) NULLABLE
  status          ENUM(active|revised|amended|withdrawn|replaced|under_review) NOT NULL
  is_purchased    BOOLEAN     DEFAULT FALSE
  purchased_at    TIMESTAMPTZ NULLABLE
  purchased_by    UUID        FK users.id NULLABLE
  purchase_notes  TEXT        NULLABLE
  source_feed_id  UUID        FK rss_feeds.id NULLABLE
  external_url    TEXT        NULLABLE
  created_at      TIMESTAMPTZ DEFAULT now()
  updated_at      TIMESTAMPTZ DEFAULT now()
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class StandardStatus(str, enum.Enum):
    active = "active"
    revised = "revised"
    amended = "amended"
    withdrawn = "withdrawn"
    replaced = "replaced"
    under_review = "under_review"


class Standard(AsyncBase):
    __tablename__ = "standards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    iso_reference: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tc_committee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[StandardStatus] = mapped_column(
        Enum(StandardStatus, name="standard_status_enum", create_type=False),
        nullable=False,
        server_default=StandardStatus.active.value,
        index=True,
    )
    is_purchased: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purchased_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    purchase_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_feed_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rss_feeds.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # M2: SHA-256 fingerprint of RSS entry fields used for change detection.
    # Nullable because standards created before M2 (or manually) have no hash.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Standard id={self.id} iso_reference={self.iso_reference}>"
