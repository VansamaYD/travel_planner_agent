"""Create immutable itinerary plans.

Revision ID: 0006_itinerary
Revises: 0005_trip_drafts
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_itinerary"
down_revision: str | None = "0005_trip_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("current_itinerary_version_id", sa.String(36), nullable=True))
    op.create_index(
        "ix_trips_current_itinerary_version_id", "trips", ["current_itinerary_version_id"]
    )
    op.create_table(
        "itinerary_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("change_type", sa.String(40), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("summary_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("trip_id", "version_no", name="uq_itinerary_version"),
    )
    for column in ("trip_id", "change_type", "created_at"):
        op.create_index(f"ix_itinerary_versions_{column}", "itinerary_versions", [column])
    op.create_table(
        "itinerary_days",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "itinerary_version_id",
            sa.String(36),
            sa.ForeignKey("itinerary_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("city_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("summary_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_itinerary_days_itinerary_version_id", "itinerary_days", ["itinerary_version_id"]
    )
    op.create_index("ix_itinerary_days_local_date", "itinerary_days", ["local_date"])
    op.create_table(
        "itinerary_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "itinerary_version_id",
            sa.String(36),
            sa.ForeignKey("itinerary_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "itinerary_day_id",
            sa.String(36),
            sa.ForeignKey("itinerary_days.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("logical_id", sa.String(36), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("title_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("place_name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("start_time", sa.String(5), nullable=True),
        sa.Column("end_time", sa.String(5), nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("execution_status", sa.String(24), nullable=False),
        sa.Column("notes_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("transport_to_next", sa.String(32), nullable=True),
        sa.Column("travel_minutes_to_next", sa.Integer(), nullable=True),
        sa.Column("travel_cost_cents_to_next", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    for column in (
        "itinerary_version_id",
        "itinerary_day_id",
        "logical_id",
        "item_type",
        "execution_status",
    ):
        op.create_index(f"ix_itinerary_items_{column}", "itinerary_items", [column])
    op.create_table(
        "itinerary_legs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "itinerary_version_id",
            sa.String(36),
            sa.ForeignKey("itinerary_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_item_logical_id", sa.String(36), nullable=False),
        sa.Column("to_item_logical_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=False),
    )
    for column in ("itinerary_version_id", "from_item_logical_id", "to_item_logical_id"):
        op.create_index(f"ix_itinerary_legs_{column}", "itinerary_legs", [column])


def downgrade() -> None:
    op.drop_table("itinerary_legs")
    op.drop_table("itinerary_items")
    op.drop_table("itinerary_days")
    op.drop_table("itinerary_versions")
    op.drop_index("ix_trips_current_itinerary_version_id", table_name="trips")
    op.drop_column("trips", "current_itinerary_version_id")
