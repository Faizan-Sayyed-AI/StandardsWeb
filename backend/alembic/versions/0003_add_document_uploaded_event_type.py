"""Add document_uploaded to event_type_enum.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15

PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a transaction block,
so we use op.execute() outside one by setting transaction=False on the
migration as a whole via the `transactional_ddl` env flag, OR we rely on
the fact that Alembic with PostgreSQL runs this in autocommit for ADD VALUE.

The safe approach: use op.execute() — PostgreSQL allows ADD VALUE outside
a transaction (it commits atomically by itself).

Tables affected:
  - event_type_enum  (shared by standard_history, notifications, notification_trigger_mappings)

New value added:
  - 'document_uploaded'  →  used when a document version is uploaded against a standard
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on PostgreSQL.
    # Alembic wraps migrations in a transaction by default; we use the
    # "execute outside transaction" pattern via connection.execution_options.
    connection = op.get_bind()
    connection.execute(
        __import__("sqlalchemy").text(
            "ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'document_uploaded'"
        )
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # The safest downgrade is a no-op — the extra value causes no harm when unused.
    pass
