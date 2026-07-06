"""Add tokens_valid_after to users for access-token revocation.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'tokens_valid_after', sa.DateTime(timezone=True), nullable=True,
        comment='JWT access tokens issued (iat) before this timestamp are rejected.'
    ))


def downgrade() -> None:
    op.drop_column('users', 'tokens_valid_after')
