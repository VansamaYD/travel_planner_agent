"""Create encrypted trip drafts and immutable versions.

Revision ID: 0005_trip_drafts
Revises: 0004_invites
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_trip_drafts"
down_revision: str | None = "0004_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("visibility", sa.String(24), nullable=False),
        sa.Column("current_version_no", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("primary_timezone", sa.String(64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("family_id", "owner_user_id", "status", "visibility", "deleted_at", "updated_at"):
        op.create_index(f"ix_trips_{column}", "trips", [column])
    op.create_table(
        "trip_requirements",
        sa.Column("trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("requirement_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trip_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_membership_id", sa.String(36), nullable=True),
        sa.Column("snapshot_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("is_temporary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trip_participants_trip_id", "trip_participants", ["trip_id"])
    op.create_index("ix_trip_participants_source_membership_id", "trip_participants", ["source_membership_id"])
    op.create_table(
        "trip_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("change_type", sa.String(40), nullable=False),
        sa.Column("snapshot_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("summary_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("trip_id", "version_no", name="uq_trip_version"),
    )
    for column in ("trip_id", "change_type", "created_by_user_id", "created_at"):
        op.create_index(f"ix_trip_versions_{column}", "trip_versions", [column])
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("event_type", "aggregate_type", "aggregate_id", "status", "available_at"):
        op.create_index(f"ix_outbox_events_{column}", "outbox_events", [column])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("trip_versions")
    op.drop_table("trip_participants")
    op.drop_table("trip_requirements")
    op.drop_table("trips")
