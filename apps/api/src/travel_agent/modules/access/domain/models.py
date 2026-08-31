from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"


class SystemRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class FamilyRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


class MemberType(StrEnum):
    ADULT = "adult"
    CHILD = "child"
    SENIOR = "senior"
    OTHER = "other"


class SensitiveVisibility(StrEnum):
    FAMILY = "family"
    PRIVATE = "private"


@dataclass(frozen=True, slots=True)
class UserIdentity:
    id: str
    username: str
    email: str | None
    display_name: str
    system_role: SystemRole
    status: UserStatus
    session_epoch: int


@dataclass(frozen=True, slots=True)
class FamilySummary:
    id: str
    name: str
    role: FamilyRole


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    id: str
    user: UserIdentity
    csrf_token: str
    expires_at: datetime
    families: tuple[FamilySummary, ...]


@dataclass(frozen=True, slots=True)
class TravelerProfile:
    nickname: str
    member_type: MemberType
    birth_year: int | None
    discount_eligibilities: tuple[str, ...]
    dietary_restrictions: tuple[str, ...]
    allergies: tuple[str, ...]
    health_notes: str
    mobility_notes: str
    travel_preferences: tuple[str, ...]
    sensitive_visibility: SensitiveVisibility
    version: int


@dataclass(frozen=True, slots=True)
class FamilyMember:
    membership_id: str
    family_id: str
    user: UserIdentity
    role: FamilyRole
    joined_at: datetime
    profile: TravelerProfile
