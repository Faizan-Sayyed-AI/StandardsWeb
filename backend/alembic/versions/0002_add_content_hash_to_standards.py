"""Add content_hash column to standards table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

content_hash stores a SHA-256 hex fingerprint of the RSS entry fields
(title + link + published + updated + summary) used by the poll_feed Celery
task to detect changes without fetching previous entries from standard_history.

No ENUMs are added in this migration — all types already exist from 0001.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "standards",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    # Index supports fast O(1) hash lookups per entry during polling
    op.create_index("ix_standards_content_hash", "standards", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_standards_content_hash", table_name="standards")
    op.drop_column("standards", "content_hash")
