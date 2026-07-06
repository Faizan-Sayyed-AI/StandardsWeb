"""Add missing indexes on FK columns (standards.purchased_by, standards.source_feed_id, documents.uploaded_by).

These were the only FK columns in the schema without an index, inconsistent
with the rest of the schema and slow for joins/lookups by purchaser or
uploader at scale.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_standards_purchased_by", "standards", ["purchased_by"])
    op.create_index("ix_standards_source_feed_id", "standards", ["source_feed_id"])
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_index("ix_standards_source_feed_id", table_name="standards")
    op.drop_index("ix_standards_purchased_by", table_name="standards")
