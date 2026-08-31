from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol, Self

from travel_agent.modules.access.domain.models import FamilyInvite, FamilyRole


class InviteStore(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def actor_role(self, family_id: str, user_id: str) -> FamilyRole | None: ...

    async def add_invite(
        self,
        *,
        invite_id: str,
        family_id: str,
        token_hash: str,
        role: FamilyRole,
        created_by_user_id: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def list_invites(self, family_id: str, now: datetime) -> tuple[FamilyInvite, ...]: ...

    async def revoke_invite(self, family_id: str, invite_id: str, now: datetime) -> bool: ...

    async def find_invite(self, token_hash: str, now: datetime) -> FamilyInvite | None: ...

    async def has_active_membership(self, family_id: str, user_id: str) -> bool: ...

    async def login_exists(self, username: str, email: str | None) -> bool: ...

    async def claim_invite(self, invite_id: str, user_id: str, accepted_at: datetime) -> bool: ...

    async def activate_membership(
        self,
        *,
        membership_id: str,
        family_id: str,
        user_id: str,
        role: FamilyRole,
        joined_at: datetime,
    ) -> None: ...

    async def add_invited_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        created_at: datetime,
    ) -> bool: ...

    async def add_audit(
        self,
        *,
        event_type: str,
        actor_user_id: str,
        subject_type: str,
        subject_id: str,
        request_id: str | None,
        details: dict[str, Any],
        created_at: datetime,
    ) -> None: ...


InviteStoreFactory = Callable[[], InviteStore]
