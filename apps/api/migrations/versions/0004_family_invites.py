"""Create single-use family invites.

Revision ID: 0004_invites
Revises: 0003_profiles
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_invites"
down_revision: str | None = "0003_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "family_id",
            sa.String(36),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in (
        "family_id",
        "token_hash",
        "status",
        "created_by_user_id",
        "expires_at",
        "accepted_by_user_id",
    ):
        op.create_index(f"ix_family_invites_{column}", "family_invites", [column])


def downgrade() -> None:
    op.drop_table("family_invites")
