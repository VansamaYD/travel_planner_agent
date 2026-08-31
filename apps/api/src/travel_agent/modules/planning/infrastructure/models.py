from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from travel_agent.shared.infrastructure.db.base import Base


class PlanningRunRow(Base):
    __tablename__ = "planning_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    profile: Mapped[str] = mapped_column(String(32))
    current_node: Mapped[str] = mapped_column(String(64))
    base_trip_version: Mapped[int] = mapped_column(Integer)
    base_itinerary_version: Mapped[int] = mapped_column(Integer)
    error_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalRow(Base):
    __tablename__ = "planning_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="CASCADE"), index=True
    )
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    base_itinerary_version: Mapped[int] = mapped_column(Integer)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(String(64))
    summary_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    rationale_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderUsageRow(Base):
    __tablename__ = "provider_usage_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(120))
    operation: Mapped[str] = mapped_column(String(80), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer)
    success: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
