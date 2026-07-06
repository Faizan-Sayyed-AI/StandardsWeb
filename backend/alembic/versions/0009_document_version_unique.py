"""Add unique constraint on documents(standard_id, version_number).

Prevents two concurrent uploads to the same standard from ever landing on
the same version_number even if the app-level row lock (see
document_service.upload_document) is ever bypassed or fails to serialize.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_documents_standard_version", "documents", ["standard_id", "version_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_standard_version", "documents", type_="unique")
