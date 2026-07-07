"""Add document_tags table for AI-generated document tags.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE document_tag_status_enum AS ENUM ('pending', 'ok', 'failed')")

    op.create_table(
        "document_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM("pending", "ok", "failed", name="document_tag_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_document_tags_document_id", table_name="document_tags")
    op.drop_table("document_tags")
    op.execute("DROP TYPE IF EXISTS document_tag_status_enum")
