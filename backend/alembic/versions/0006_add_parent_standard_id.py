"""Add parent_standard_id to standards for amendment tracking.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "standards",
        sa.Column(
            "parent_standard_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_standards_parent_standard_id",
        "standards",
        "standards",
        ["parent_standard_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_standards_parent_standard_id",
        "standards",
        ["parent_standard_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_standards_parent_standard_id", table_name="standards")
    op.drop_constraint(
        "fk_standards_parent_standard_id", "standards", type_="foreignkey"
    )
    op.drop_column("standards", "parent_standard_id")
