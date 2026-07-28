"""Add api_keys table and rss_feeds.api_key_id.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-27

Adds the api_keys pool so RSS feeds can be distributed across multiple
rss2json.com API keys (each key is capped at a fixed number of feeds).

api_key_id is added NULLABLE — existing feed rows are backfilled by
scripts/backfill_api_keys.py, run manually after this migration (same
pattern as migration 0007 / scripts/backfill_base_reference.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE api_key_status_enum AS ENUM "
        "('active', 'rate_limited', 'expired', 'disabled')"
    )

    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("key_value", sa.Text(), nullable=False),
        sa.Column("capacity", sa.SmallInteger(), nullable=False, server_default="25"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "rate_limited", "expired", "disabled",
                name="api_key_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("consecutive_failures", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label"),
    )

    op.add_column(
        "rss_feeds",
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rss_feeds_api_key_id",
        "rss_feeds",
        "api_keys",
        ["api_key_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_rss_feeds_api_key_id", "rss_feeds", ["api_key_id"])


def downgrade() -> None:
    op.drop_index("ix_rss_feeds_api_key_id", table_name="rss_feeds")
    op.drop_constraint("fk_rss_feeds_api_key_id", "rss_feeds", type_="foreignkey")
    op.drop_column("rss_feeds", "api_key_id")

    op.drop_table("api_keys")
    op.execute("DROP TYPE IF EXISTS api_key_status_enum")
