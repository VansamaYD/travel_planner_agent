from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from travel_agent.shared.infrastructure.db.base import Base


class ItineraryVersionRow(Base):
    __tablename__ = "itinerary_versions"
    __table_args__ = (Index("uq_itinerary_version", "trip_id", "version_no", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = mapped_column(String(36))
    change_type: Mapped[str] = mapped_column(String(40), index=True)
    snapshot_schema_version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    summary_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ItineraryDayRow(Base):
    __tablename__ = "itinerary_days"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    itinerary_version_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_versions.id", ondelete="CASCADE"), index=True
    )
    local_date: Mapped[date] = mapped_column(Date, index=True)
    city_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    summary_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    sort_order: Mapped[int] = mapped_column(Integer)


class ItineraryItemRow(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    itinerary_version_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_versions.id", ondelete="CASCADE"), index=True
    )
    itinerary_day_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_days.id", ondelete="CASCADE"), index=True
    )
    logical_id: Mapped[str] = mapped_column(String(36), index=True)
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    title_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    place_name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    start_time: Mapped[str | None] = mapped_column(String(5))
    end_time: Mapped[str | None] = mapped_column(String(5))
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    execution_status: Mapped[str] = mapped_column(String(24), index=True)
    notes_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    transport_to_next: Mapped[str | None] = mapped_column(String(32))
    travel_minutes_to_next: Mapped[int | None] = mapped_column(Integer)
    travel_cost_cents_to_next: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)


class ItineraryLegRow(Base):
    __tablename__ = "itinerary_legs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    itinerary_version_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_versions.id", ondelete="CASCADE"), index=True
    )
    from_item_logical_id: Mapped[str] = mapped_column(String(36), index=True)
    to_item_logical_id: Mapped[str] = mapped_column(String(36), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    cost_cents: Mapped[int | None] = mapped_column(Integer)
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
