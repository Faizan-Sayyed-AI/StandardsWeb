"""
ORM models: email_digest_queue and email_digest_runs tables.

email_digest_queue holds one row per notification event that is waiting to be
included in the next weekly digest email. digest_run_id is NULL while pending
and set to the run that sent (or is sending) the row.

email_digest_runs has one row per digest send. slot_key (the local calendar date
of the slot) is UNIQUE, which is what makes the dispatcher idempotent — a second
beat, a retry, or an hourly catch-up tick cannot send the same slot twice.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncBase


class EmailDigestRun(AsyncBase):
    __tablename__ = "email_digest_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slot_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class EmailDigestQueueItem(AsyncBase):
    __tablename__ = "email_digest_queue"
    __table_args__ = (
        Index("ix_email_digest_queue_pending", "digest_run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "new", "updated", "amended", "withdrawn", "replaced",
            "purchased", "status_change", "document_uploaded",
            name="event_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    standard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standards.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    digest_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_digest_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
