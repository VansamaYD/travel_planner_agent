"""Create external tool cache, usage ledger and guide candidates.

Revision ID: 0009_external_tools
Revises: 0008_conversations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_external_tools"
down_revision: str | None = "0008_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_cache_entries",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_external_cache_expiry", "external_cache_entries", ["expires_at", "stale_until"]
    )
    op.create_table(
        "external_usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("cache_status", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_external_usage_owner_created",
        "external_usage_events",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "guide_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id_hash", sa.String(64), nullable=False),
        sa.Column("title_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("url_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("author_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("summary_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_user_id", "provider", "external_id_hash", name="uq_guide_candidate_source"
        ),
    )
    op.create_index(
        "ix_guide_candidates_owner_fetched",
        "guide_candidates",
        ["owner_user_id", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_table("guide_candidates")
    op.drop_table("external_usage_events")
    op.drop_table("external_cache_entries")
