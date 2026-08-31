from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from travel_agent.modules.trips.domain.models import TripDraft, TripListItem, TripVersion


class TripStore(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def actor_role(self, family_id: str, user_id: str) -> str | None: ...

    async def participant_snapshots(
        self, family_id: str, membership_ids: tuple[str, ...], actor_user_id: str
    ) -> tuple[dict[str, object], ...]: ...

    async def create(
        self, draft: TripDraft, actor_user_id: str, request_id: str | None
    ) -> None: ...

    async def list_visible(
        self, user_id: str, family_id: str | None
    ) -> tuple[TripListItem, ...]: ...

    async def get(self, trip_id: str) -> TripDraft | None: ...

    async def get_including_deleted(self, trip_id: str) -> tuple[TripDraft, bool] | None: ...

    async def list_deleted(
        self, user_id: str, family_id: str | None
    ) -> tuple[TripListItem, ...]: ...

    async def update(
        self,
        draft: TripDraft,
        expected_version: int,
        change_type: str,
        summary: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> bool: ...

    async def list_versions(self, trip_id: str) -> tuple[TripVersion, ...]: ...

    async def get_version(self, trip_id: str, version_no: int) -> TripVersion | None: ...

    async def set_deleted(
        self,
        trip_id: str,
        *,
        deleted: bool,
        actor_user_id: str,
        request_id: str | None,
        changed_at: datetime,
    ) -> bool: ...

    async def commit(self) -> None: ...


class TripStoreFactory(Protocol):
    def __call__(self) -> TripStore: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
