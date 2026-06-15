"""
ORM model: documents table.

Schema (PRD §6.2):
  id               UUID      PK
  standard_id      UUID      FK standards.id NOT NULL
  version_number   SMALLINT  NOT NULL  (auto-incremented per standard)
  filename         VARCHAR(255) NOT NULL
  storage_path     TEXT      NOT NULL  (FS path or S3 key)
  file_size_bytes  BIGINT    NOT NULL
  sha256_checksum  CHAR(64)  NOT NULL  (SHA-256 hex digest)
  mime_type        VARCHAR(100) NOT NULL
  change_notes     TEXT      NULLABLE
  uploaded_by      UUID      FK users.id NOT NULL
  uploaded_at      TIMESTAMPTZ DEFAULT now()
  is_current       BOOLEAN   DEFAULT TRUE  (latest version flag)
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class Document(AsyncBase):
    __tablename__ = "documents"

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
    version_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    change_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    def __repr__(self) -> str:
        return f"<Document id={self.id} standard_id={self.standard_id} v{self.version_number}>"
