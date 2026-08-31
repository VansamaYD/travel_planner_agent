from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ItineraryItem:
    logical_id: str
    item_type: str
    title: str
    place_name: str
    start_time: str | None
    end_time: str | None
    cost_cents: int | None
    execution_status: str
    notes: str
    tags: tuple[str, ...]
    transport_to_next: str | None
    travel_minutes_to_next: int | None
    travel_cost_cents_to_next: int | None


@dataclass(frozen=True, slots=True)
class ItineraryDay:
    id: str
    local_date: date
    city: str
    summary: str
    items: tuple[ItineraryItem, ...]


@dataclass(frozen=True, slots=True)
class ItineraryPlan:
    id: str
    trip_id: str
    version: int
    days: tuple[ItineraryDay, ...]
    currency: str
    estimated_total_cost_cents: int
    warnings: tuple[str, ...]
    created_by_user_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ItineraryVersionSummary:
    id: str
    trip_id: str
    version: int
    change_type: str
    summary: str
    created_by_user_id: str
    created_at: datetime
