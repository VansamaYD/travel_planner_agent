from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import date, timedelta

from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.planning.application.errors import (
    PlanningError,
    PlanningInvalidInputError,
    PlanningNotFoundError,
    PlanningPermissionDeniedError,
    PlanningVersionConflictError,
)
from travel_agent.modules.planning.application.ports import (
    Clock,
    ModelProvider,
    PlanningStore,
    PlanningStoreFactory,
)
from travel_agent.modules.planning.domain.models import ModelUsage, PlanningRun, Proposal
from travel_agent.shared.domain.ids import new_uuid7


class PlanningService:
    def __init__(
        self,
        store_factory: PlanningStoreFactory,
        provider: ModelProvider,
        clock: Clock,
        provider_name: str,
        model_name: str,
    ) -> None:
        self._store_factory, self._provider, self._clock = store_factory, provider, clock
        self._provider_name, self._model_name = provider_name, model_name

    async def start(
        self,
        session: AuthenticatedSession,
        csrf: str | None,
        trip_id: str,
        profile: str,
        instruction: str,
        request_id: str | None,
    ) -> tuple[PlanningRun, Proposal | None]:
        self._csrf(session, csrf)
        now = self._clock.now()
        async with self._store_factory() as store:
            context = await self._authorize(store, session.user.id, trip_id, write=True)
            requirements = context.get("requirements")
            if not isinstance(requirements, dict) or not requirements.get("confirmed"):
                raise PlanningInvalidInputError(
                    "请先确认旅行需求，再启动智能规划。"  # noqa: RUF001
                )
            run = PlanningRun(
                new_uuid7(),
                trip_id,
                "running",
                profile,
                "itinerary_designer",
                self._integer(context["trip_version"]),
                self._integer(context.get("itinerary_version", 0)),
                "",
                now,
                None,
            )
            await store.create_run(run, session.user.id, request_id)
            await store.commit()
        usage: ModelUsage | None = None
        try:
            result = await self._provider.generate_itinerary(
                self._model_context(context, instruction, profile)
            )
            usage = result.usage
            self._validate_dates(result.days, requirements)
            completed = self._clock.now()
            proposal = Proposal(
                new_uuid7(),
                run.id,
                trip_id,
                "pending",
                run.base_itinerary_version,
                result.summary,
                result.rationale,
                result.days,
                result.warnings,
                result.usage,
                completed,
                None,
            )
            finished = replace(
                run, status="succeeded", current_node="approval_gate", completed_at=completed
            )
            async with self._store_factory() as store:
                await store.succeed(
                    finished,
                    proposal,
                    self._provider_name,
                    self._model_name,
                    session.user.id,
                    request_id,
                )
                await store.commit()
            return finished, proposal
        except PlanningError as error:
            failed = replace(run, status="failed", error=str(error), completed_at=self._clock.now())
            async with self._store_factory() as store:
                await store.fail(
                    failed,
                    usage,
                    self._provider_name,
                    self._model_name,
                    session.user.id,
                    request_id,
                )
                await store.commit()
            return failed, None
        except Exception:
            failed = replace(
                run,
                status="failed",
                error="模型调用或结构化校验失败。",
                completed_at=self._clock.now(),
            )
            async with self._store_factory() as store:
                await store.fail(
                    failed,
                    usage,
                    self._provider_name,
                    self._model_name,
                    session.user.id,
                    request_id,
                )
                await store.commit()
            return failed, None

    async def get_run(self, session: AuthenticatedSession, run_id: str) -> PlanningRun:
        async with self._store_factory() as store:
            run = await store.get_run(run_id)
            if run is None:
                raise PlanningNotFoundError
            await self._authorize(store, session.user.id, run.trip_id, write=False)
            return run

    async def proposals(self, session: AuthenticatedSession, trip_id: str) -> tuple[Proposal, ...]:
        async with self._store_factory() as store:
            await self._authorize(store, session.user.id, trip_id, write=False)
            return await store.list_proposals(trip_id)

    async def proposal(self, session: AuthenticatedSession, proposal_id: str) -> Proposal:
        async with self._store_factory() as store:
            value = await store.get_proposal(proposal_id)
            if value is None:
                raise PlanningNotFoundError
            await self._authorize(store, session.user.id, value.trip_id, write=False)
            return value

    async def mark_applied(
        self,
        session: AuthenticatedSession,
        csrf: str | None,
        proposal_id: str,
        request_id: str | None,
    ) -> None:
        self._csrf(session, csrf)
        async with self._store_factory() as store:
            value = await store.get_proposal(proposal_id)
            if value is None:
                raise PlanningNotFoundError
            await self._authorize(store, session.user.id, value.trip_id, write=True)
            if not await store.mark_applied(
                proposal_id,
                "pending",
                self._clock.now(),
                session.user.id,
                request_id,
            ):
                raise PlanningVersionConflictError
            await store.commit()

    @staticmethod
    async def _authorize(
        store: PlanningStore, user_id: str, trip_id: str, *, write: bool
    ) -> dict[str, object]:
        context = await store.trip_context(trip_id)
        if context is None:
            raise PlanningNotFoundError
        role = await store.actor_role(str(context["family_id"]), user_id)
        if write and str(context["owner_user_id"]) != user_id and role not in {"owner", "admin"}:
            raise PlanningPermissionDeniedError
        if (
            not write
            and str(context["owner_user_id"]) != user_id
            and (str(context["visibility"]) == "private" or role is None)
        ):
            raise PlanningPermissionDeniedError
        return context

    @staticmethod
    def _integer(value: object) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise PlanningInvalidInputError("旅行版本数据无效。")

    @staticmethod
    def _model_context(
        context: dict[str, object], instruction: str, profile: str
    ) -> dict[str, object]:
        participant_fields = (
            "member_type",
            "birth_year",
            "discount_eligibilities",
            "dietary_restrictions",
            "allergies",
            "health_notes",
            "mobility_notes",
            "travel_preferences",
        )
        raw_participants = context.get("participants")
        participants = (
            [
                {
                    "traveler": f"同行者{index + 1}",
                    **{field: value.get(field) for field in participant_fields},
                }
                for index, value in enumerate(raw_participants)
                if isinstance(value, dict)
            ]
            if isinstance(raw_participants, list)
            else []
        )
        current = context.get("current_itinerary")
        itinerary = None
        if isinstance(current, dict):
            itinerary = {
                "days": current.get("days", []),
                "currency": current.get("currency", "CNY"),
                "estimated_total_cost_cents": current.get("estimated_total_cost_cents", 0),
            }
        return {
            "requirements": context.get("requirements", {}),
            "participants": participants,
            "current_itinerary": itinerary,
            "instruction": instruction,
            "profile": profile,
        }

    @staticmethod
    def _csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
            raise PlanningPermissionDeniedError

    @staticmethod
    def _validate_dates(
        days: tuple[dict[str, object], ...], requirements: dict[str, object]
    ) -> None:
        start_raw, end_raw = requirements.get("start_date"), requirements.get("end_date")
        if not isinstance(start_raw, str) or not isinstance(end_raw, str):
            raise PlanningInvalidInputError("智能规划需要完整的出发和结束日期。")
        try:
            start, end = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
            expected = tuple(
                (start + timedelta(days=offset)).isoformat()
                for offset in range((end - start).days + 1)
            )
        except ValueError as error:
            raise PlanningInvalidInputError("旅行日期格式无效。") from error
        actual = tuple(str(day.get("local_date", "")) for day in days)
        if actual != expected:
            raise PlanningInvalidInputError(
                "模型提案未完整、按顺序覆盖旅行日期，已拒绝入库。"  # noqa: RUF001
            )
