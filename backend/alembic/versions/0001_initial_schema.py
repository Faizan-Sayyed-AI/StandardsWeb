"""Initial schema — all 13 tables.

Revision ID: 0001
Revises: (none — this is the first migration)
Create Date: 2026-06-14

Creates all PostgreSQL ENUM types, then all tables in FK-dependency order.
Adds composite indexes as specified in PRD §15.3.

Tables created:
  1.  users
  2.  rss_feeds
  3.  standards
  4.  standard_history
  5.  documents
  6.  distribution_lists
  7.  distribution_list_members
  8.  notification_trigger_mappings
  9.  notifications
  10. audit_logs
  11. celery_schedules
  12. refresh_tokens
  13. password_reset_tokens
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- 1. Create all PostgreSQL ENUM types first
    op.execute("CREATE TYPE user_role_enum AS ENUM ('admin', 'manager', 'viewer')")
    op.execute("CREATE TYPE schedule_type_enum AS ENUM ('daily', 'weekly')")
    op.execute("CREATE TYPE poll_status_enum AS ENUM ('pending', 'ok', 'failed')")
    op.execute("CREATE TYPE standard_status_enum AS ENUM ('active', 'revised', 'amended', 'withdrawn', 'replaced', 'under_review')")
    op.execute("CREATE TYPE event_type_enum AS ENUM ('new', 'updated', 'amended', 'withdrawn', 'replaced', 'purchased', 'status_change')")
    op.execute("CREATE TYPE event_source_enum AS ENUM ('rss', 'manual', 'system')")
    op.execute("CREATE TYPE notification_severity_enum AS ENUM ('info', 'warning', 'critical')")
    # ── 1. Create all PostgreSQL ENUM types first ──────────────────────────
                # ── 2. users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("admin", "manager", "viewer", name="user_role_enum", create_type=False),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── 3. rss_feeds ─────────────────────────────────────────────────────
    op.create_table(
        "rss_feeds",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("tc_committee", sa.String(100), nullable=True),
        sa.Column(
            "schedule_type",
            postgresql.ENUM("daily", "weekly", name="schedule_type_enum", create_type=False),
            nullable=False,
            server_default="daily",
        ),
        sa.Column("schedule_hour", sa.SmallInteger(), nullable=False, server_default="6"),
        sa.Column("schedule_day_of_week", sa.SmallInteger(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_poll_status",
            postgresql.ENUM("pending", "ok", "failed", name="poll_status_enum", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("failure_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )

    # ── 4. standards ─────────────────────────────────────────────────────
    op.create_table(
        "standards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("iso_reference", sa.String(100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("edition", sa.String(50), nullable=True),
        sa.Column("tc_committee", sa.String(100), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "revised", "amended", "withdrawn", "replaced", "under_review",
                name="standard_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("is_purchased", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchased_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purchase_notes", sa.Text(), nullable=True),
        sa.Column("source_feed_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["purchased_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_feed_id"], ["rss_feeds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("iso_reference"),
    )
    op.create_index("ix_standards_iso_reference", "standards", ["iso_reference"])
    # PRD §15.3: composite index for filtered list queries
    op.create_index(
        "ix_standards_status_is_purchased",
        "standards",
        ["status", "is_purchased"],
    )

    # ── 5. standard_history ──────────────────────────────────────────────
    op.create_table(
        "standard_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("standard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "new", "updated", "amended", "withdrawn", "replaced", "purchased", "status_change",
                name="event_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM("rss", "manual", "system", name="event_source_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["standard_id"], ["standards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_standard_history_standard_id", "standard_history", ["standard_id"])
    op.create_index("ix_standard_history_created_at", "standard_history", ["created_at"])

    # ── 6. documents ─────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("standard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.SmallInteger(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("change_notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["standard_id"], ["standards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_standard_id", "documents", ["standard_id"])

    # ── 7. distribution_lists ────────────────────────────────────────────
    op.create_table(
        "distribution_lists",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ── 8. distribution_list_members ─────────────────────────────────────
    op.create_table(
        "distribution_list_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("list_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["list_id"], ["distribution_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "email", name="uq_list_member_email"),
    )
    op.create_index(
        "ix_distribution_list_members_list_id", "distribution_list_members", ["list_id"]
    )

    # ── 9. notification_trigger_mappings ─────────────────────────────────
    op.create_table(
        "notification_trigger_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "new", "updated", "amended", "withdrawn", "replaced", "purchased", "status_change",
                name="event_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("list_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notify_all_users", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["list_id"], ["distribution_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_trigger_mappings_event_type",
        "notification_trigger_mappings",
        ["event_type"],
    )

    # ── 10. notifications ────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "new", "updated", "amended", "withdrawn", "replaced", "purchased", "status_change",
                name="event_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "info", "warning", "critical",
                name="notification_severity_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="info",
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("related_standard_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["related_standard_id"], ["standards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # PRD §15.3: composite index for unread notification queries
    op.create_index(
        "ix_notifications_user_id_is_read", "notifications", ["user_id", "is_read"]
    )

    # ── 11. audit_logs ───────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── 12. celery_schedules ─────────────────────────────────────────────
    op.create_table(
        "celery_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["feed_id"], ["rss_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_celery_schedules_feed_id", "celery_schedules", ["feed_id"])

    # ── 13. refresh_tokens ───────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ── 14. password_reset_tokens ────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    # Drop tables in reverse FK-dependency order
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("celery_schedules")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("notification_trigger_mappings")
    op.drop_table("distribution_list_members")
    op.drop_table("distribution_lists")
    op.drop_table("documents")
    op.drop_table("standard_history")
    op.drop_table("standards")
    op.drop_table("rss_feeds")
    op.drop_table("users")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS notification_severity_enum")
    op.execute("DROP TYPE IF EXISTS event_source_enum")
    op.execute("DROP TYPE IF EXISTS event_type_enum")
    op.execute("DROP TYPE IF EXISTS standard_status_enum")
    op.execute("DROP TYPE IF EXISTS poll_status_enum")
    op.execute("DROP TYPE IF EXISTS schedule_type_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")



