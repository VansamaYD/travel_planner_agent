from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class TripStatus(StrEnum):
    DRAFT = "draft"


class TripVisibility(StrEnum):
    PRIVATE = "private"
    FAMILY = "family"


class TripInputMode(StrEnum):
    FORM = "form"
    CHAT = "chat"
    IMPORT = "import"


@dataclass(frozen=True, slots=True)
class TripRequirements:
    input_mode: TripInputMode
    origin: str
    destinations: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    budget_cents: int | None
    currency: str
    styles: tuple[str, ...]
    pace: str
    transportation: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]
    assumptions: tuple[str, ...]
    source_text: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class TripParticipant:
    id: str
    source_membership_id: str | None
    display_name: str
    member_type: str
    birth_year: int | None
    discount_eligibilities: tuple[str, ...]
    dietary_restrictions: tuple[str, ...]
    allergies: tuple[str, ...]
    health_notes: str
    mobility_notes: str
    travel_preferences: tuple[str, ...]
    is_temporary: bool


@dataclass(frozen=True, slots=True)
class TripDraft:
    id: str
    family_id: str
    owner_user_id: str
    title: str
    status: TripStatus
    visibility: TripVisibility
    version: int
    requirements: TripRequirements
    participants: tuple[TripParticipant, ...]
    warnings: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TripListItem:
    id: str
    family_id: str
    owner_user_id: str
    title: str
    status: TripStatus
    visibility: TripVisibility
    version: int
    origin: str
    destinations: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    participant_count: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TripVersion:
    id: str
    trip_id: str
    version_no: int
    change_type: str
    summary: str
    created_by_user_id: str
    created_at: datetime
    snapshot: TripDraft | None = None
