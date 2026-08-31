"""Create encrypted traveler profiles.

Revision ID: 0003_profiles
Revises: 0002_access
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_profiles"
down_revision: str | None = "0002_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traveler_profiles",
        sa.Column(
            "membership_id",
            sa.String(36),
            sa.ForeignKey("family_memberships.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profile_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_traveler_profiles_updated_by_user_id",
        "traveler_profiles",
        ["updated_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("traveler_profiles")
