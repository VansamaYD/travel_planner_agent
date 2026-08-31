from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol, Self

from travel_agent.modules.access.domain.models import FamilyMember, FamilyRole, TravelerProfile


class MemberStore(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def actor_role(self, family_id: str, user_id: str) -> FamilyRole | None: ...

    async def list_members(self, family_id: str) -> tuple[FamilyMember, ...]: ...

    async def get_member(self, family_id: str, membership_id: str) -> FamilyMember | None: ...

    async def login_exists(self, username: str, email: str | None) -> bool: ...

    async def create_member(
        self,
        *,
        family_id: str,
        user_id: str,
        membership_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        role: FamilyRole,
        profile: TravelerProfile,
        actor_user_id: str,
        created_at: datetime,
    ) -> bool: ...

    async def save_profile(
        self,
        *,
        membership_id: str,
        expected_version: int,
        profile: TravelerProfile,
        actor_user_id: str,
        updated_at: datetime,
    ) -> bool: ...

    async def set_role(self, membership_id: str, role: FamilyRole) -> None: ...

    async def remove_membership(self, membership_id: str) -> None: ...

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


MemberStoreFactory = Callable[[], MemberStore]
