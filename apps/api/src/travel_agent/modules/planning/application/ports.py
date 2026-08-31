from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from travel_agent.modules.planning.domain.models import ModelUsage, PlanningRun, Proposal


class ModelResult(Protocol):
    @property
    def days(self) -> tuple[dict[str, object], ...]: ...

    @property
    def summary(self) -> str: ...

    @property
    def rationale(self) -> str: ...

    @property
    def warnings(self) -> tuple[str, ...]: ...

    @property
    def usage(self) -> ModelUsage: ...


class ModelProvider(Protocol):
    async def generate_itinerary(self, context: dict[str, object]) -> ModelResult: ...


class PlanningStore(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def trip_context(self, trip_id: str) -> dict[str, object] | None: ...
    async def actor_role(self, family_id: str, user_id: str) -> str | None: ...
    async def create_run(
        self, run: PlanningRun, actor_user_id: str, request_id: str | None
    ) -> None: ...
    async def succeed(
        self,
        run: PlanningRun,
        proposal: Proposal,
        provider: str,
        model: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> None: ...
    async def fail(
        self,
        run: PlanningRun,
        usage: ModelUsage | None,
        provider: str,
        model: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> None: ...
    async def get_run(self, run_id: str) -> PlanningRun | None: ...
    async def get_proposal(self, proposal_id: str) -> Proposal | None: ...
    async def list_proposals(self, trip_id: str) -> tuple[Proposal, ...]: ...
    async def mark_applied(
        self,
        proposal_id: str,
        expected_status: str,
        applied_at: datetime,
        actor_user_id: str,
        request_id: str | None,
    ) -> bool: ...
    async def commit(self) -> None: ...


class PlanningStoreFactory(Protocol):
    def __call__(self) -> PlanningStore: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
