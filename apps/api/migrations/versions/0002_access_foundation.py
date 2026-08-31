"""Create access, session, family, and audit tables.

Revision ID: 0002_access
Revises: 0001_slice0
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_access"
down_revision: str | None = "0001_slice0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_code_hash", sa.Text(), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "system_state",
            sa.column("id", sa.Integer()),
            sa.column("initialized_at", sa.DateTime(timezone=True)),
            sa.column("recovery_code_hash", sa.Text()),
        ),
        [{"id": 1, "initialized_at": None, "recovery_code_hash": None}],
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username_normalized", sa.String(128), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=True),
        sa.Column("display_name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("system_role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username_normalized"),
        sa.UniqueConstraint("email_normalized"),
    )
    op.create_index("ix_users_username_normalized", "users", ["username_normalized"])
    op.create_index("ix_users_email_normalized", "users", ["email_normalized"])
    op.create_index("ix_users_system_role", "users", ["system_role"])
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "families",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("default_locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("storage_limit_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "family_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "family_id",
            sa.String(36),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_family_memberships_family_id", "family_memberships", ["family_id"])
    op.create_index("ix_family_memberships_user_id", "family_memberships", ["user_id"])
    op.create_index("ix_family_memberships_role", "family_memberships", ["role"])
    op.create_index("ix_family_memberships_status", "family_memberships", ["status"])
    op.create_index(
        "uq_family_membership", "family_memberships", ["family_id", "user_id"], unique=True
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("session_epoch", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index("ix_sessions_revoked_at", "sessions", ["revoked_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("subject_type", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "event_type",
        "actor_user_id",
        "source_type",
        "subject_type",
        "subject_id",
        "request_id",
        "created_at",
    ):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("sessions")
    op.drop_table("family_memberships")
    op.drop_table("families")
    op.drop_table("users")
    op.drop_table("system_state")
