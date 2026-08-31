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
