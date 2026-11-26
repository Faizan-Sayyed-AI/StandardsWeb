"""Add email digest queue and run tables.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-26

Supports the weekly email digest: notification events are queued in
email_digest_queue instead of being emailed one by one, and a scheduled task
compiles them into a single email per recipient. email_digest_runs records each
send and its unique slot_key makes the run idempotent.

Purely additive — no existing table is touched, and digest mode is off by
default (EMAIL_DIGEST_ENABLED), so applying this migration changes no behaviour.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_digest_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slot_key", sa.String(32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_key", name="uq_email_digest_runs_slot_key"),
    )

    op.create_table(
        "email_digest_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="event_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("standard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("triggered_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("digest_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["standard_id"], ["standards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["digest_run_id"], ["email_digest_runs.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_email_digest_queue_pending",
        "email_digest_queue",
        ["digest_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_digest_queue_pending", table_name="email_digest_queue")
    op.drop_table("email_digest_queue")
    op.drop_table("email_digest_runs")
