"""Add base_reference to standards for base-number grouping.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('standards', sa.Column(
        'base_reference', sa.String(50), nullable=True,
        comment='Base standard number e.g. 3651-2 for ISO/WD 3651-2 and ISO 3651-2:1998'
    ))
    op.create_index('ix_standards_base_reference', 'standards', ['base_reference'])


def downgrade() -> None:
    op.drop_index('ix_standards_base_reference', table_name='standards')
    op.drop_column('standards', 'base_reference')
