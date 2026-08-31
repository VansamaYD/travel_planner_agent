from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol, Self

from travel_agent.modules.access.domain.models import (
    AuthenticatedSession,
    FamilyRole,
    FamilySummary,
    SystemRole,
    UserIdentity,
)


@dataclass(frozen=True, slots=True)
class CredentialRecord:
    identity: UserIdentity
    password_hash: str


class PasswordHasher(Protocol):
    async def hash(self, secret: str) -> str: ...

    async def verify(self, encoded_hash: str, secret: str) -> bool: ...


class TokenIssuer(Protocol):
    def session_token(self) -> str: ...

    def csrf_token(self) -> str: ...

    def recovery_code(self) -> str: ...

    def invite_code(self) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AccessStore(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def is_initialized(self) -> bool: ...

    async def claim_initialization(self, initialized_at: datetime, recovery_hash: str) -> bool: ...

    async def add_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        system_role: SystemRole,
        created_at: datetime,
    ) -> UserIdentity: ...

    async def add_family(
        self, *, family_id: str, name: str, owner_user_id: str, created_at: datetime
    ) -> None: ...

    async def add_membership(
        self,
        *,
        membership_id: str,
        family_id: str,
        user_id: str,
        role: FamilyRole,
        joined_at: datetime,
    ) -> None: ...

    async def find_user_by_login(self, normalized_login: str) -> CredentialRecord | None: ...

    async def mark_login(self, user_id: str, logged_in_at: datetime) -> None: ...

    async def add_session(
        self,
        *,
        session_id: str,
        token_hash: str,
        csrf_token: str,
        user_id: str,
        session_epoch: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def get_session(self, token_hash: str, now: datetime) -> AuthenticatedSession | None: ...

    async def revoke_session(self, session_id: str, revoked_at: datetime) -> None: ...

    async def list_families(self, user_id: str) -> tuple[FamilySummary, ...]: ...

    async def add_audit(
        self,
        *,
        event_type: str,
        actor_user_id: str | None,
        subject_type: str,
        subject_id: str | None,
        request_id: str | None,
        details: dict[str, Any],
        created_at: datetime,
    ) -> None: ...


AccessStoreFactory = Callable[[], AccessStore]
