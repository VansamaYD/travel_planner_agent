"""Create planning runs, proposals and provider usage ledger.

Revision ID: 0007_planning
Revises: 0006_itinerary
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_planning"
down_revision: str | None = "0006_itinerary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("current_node", sa.String(64), nullable=False),
        sa.Column("base_trip_version", sa.Integer(), nullable=False),
        sa.Column("base_itinerary_version", sa.Integer(), nullable=False),
        sa.Column("error_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for c in ("trip_id", "status", "created_at"):
        op.create_index(f"ix_planning_runs_{c}", "planning_runs", [c])
    op.create_table(
        "planning_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("planning_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trip_id", sa.String(36), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("base_itinerary_version", sa.Integer(), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("summary_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("rationale_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    for c in ("run_id", "trip_id", "status", "created_at"):
        op.create_index(f"ix_planning_proposals_{c}", "planning_proposals", [c])
    op.create_table(
        "provider_usage_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_microusd", sa.Integer(), nullable=False),
        sa.Column("success", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for c in ("run_id", "provider", "operation", "created_at"):
        op.create_index(f"ix_provider_usage_records_{c}", "provider_usage_records", [c])


def downgrade() -> None:
    op.drop_table("provider_usage_records")
    op.drop_table("planning_proposals")
    op.drop_table("planning_runs")
