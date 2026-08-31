from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    estimated_cost_microusd: int


@dataclass(frozen=True, slots=True)
class PlanningRun:
    id: str
    trip_id: str
    status: str
    profile: str
    current_node: str
    base_trip_version: int
    base_itinerary_version: int
    error: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class Proposal:
    id: str
    run_id: str
    trip_id: str
    status: str
    base_itinerary_version: int
    summary: str
    rationale: str
    days: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    usage: ModelUsage
    created_at: datetime
    applied_at: datetime | None
