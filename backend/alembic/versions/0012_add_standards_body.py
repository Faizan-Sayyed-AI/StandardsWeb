"""Add standards_body to standards (ISO/IEC/IEEE/ASTM/Other).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('standards', sa.Column(
        'standards_body', sa.String(50), nullable=True,
        comment="Issuing body (ISO, IEC, IEEE, ASTM, or free text via 'Other') — "
                "populated for both feed-sourced and manually-created standards."
    ))
    op.create_index('ix_standards_standards_body', 'standards', ['standards_body'])


def downgrade() -> None:
    op.drop_index('ix_standards_standards_body', table_name='standards')
    op.drop_column('standards', 'standards_body')
