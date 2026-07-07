"""
ORM model: document_tags table.

One row per document version, created eagerly at upload time (status=pending)
and filled in asynchronously by the app.tasks.documents.tag_document Celery
task. See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class DocumentTagStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    failed = "failed"


class DocumentTag(AsyncBase):
    __tablename__ = "document_tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[DocumentTagStatus] = mapped_column(
        Enum(DocumentTagStatus, name="document_tag_status_enum", create_type=False),
        nullable=False,
        server_default=DocumentTagStatus.pending.value,
    )
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DocumentTag id={self.id} document_id={self.document_id} status={self.status}>"
