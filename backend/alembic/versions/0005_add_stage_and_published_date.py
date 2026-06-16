"""Add stage and published date to standards.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("standards", sa.Column("stage_code", sa.String(length=10), nullable=True))
    op.add_column("standards", sa.Column("stage_name", sa.String(length=100), nullable=True))
    op.add_column("standards", sa.Column("published_date", sa.Date(), nullable=True))
    
    op.create_index("ix_standards_published_date", "standards", ["published_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_standards_published_date", table_name="standards")
    op.drop_column("standards", "published_date")
    op.drop_column("standards", "stage_name")
    op.drop_column("standards", "stage_code")
