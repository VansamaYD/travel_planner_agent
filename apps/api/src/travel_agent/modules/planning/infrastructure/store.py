from __future__ import annotations

import json
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self, cast

from sqlalchemy import select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.planning.domain.models import ModelUsage, PlanningRun, Proposal
from travel_agent.modules.planning.infrastructure.models import (
    PlanningRunRow,
    ProposalRow,
    ProviderUsageRow,
)
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, value: str, *, context: str) -> bytes: ...
    def decrypt(self, payload: bytes, *, context: str) -> str: ...
    def digest(self, value: str, *, context: str) -> str: ...


class SqlAlchemyPlanningStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], protector: TextProtector
    ) -> None:
        self._session_factory = session_factory
        self._protector = protector
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Planning store is not active")
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        await self.session.commit()

    async def actor_role(self, family_id: str, user_id: str) -> str | None:
        result = await self.session.execute(
            text(
                "SELECT role FROM family_memberships "
                "WHERE family_id=:family AND user_id=:user AND status='active'"
            ),
            {"family": family_id, "user": user_id},
        )
        return cast(str | None, result.scalar_one_or_none())

    async def trip_context(self, trip_id: str) -> dict[str, object] | None:
        record = (
            await self.session.execute(
                text(
                    "SELECT t.family_id,t.owner_user_id,t.visibility,t.current_version_no,"
                    "t.current_itinerary_version_id,tv.snapshot_ciphertext,iv.version_no,"
                    "iv.snapshot_ciphertext FROM trips t JOIN trip_versions tv "
                    "ON tv.trip_id=t.id AND tv.version_no=t.current_version_no "
                    "LEFT JOIN itinerary_versions iv ON iv.id=t.current_itinerary_version_id "
                    "WHERE t.id=:trip AND t.deleted_at IS NULL"
                ),
                {"trip": trip_id},
            )
        ).one_or_none()
        if record is None:
            return None
        (
            family,
            owner,
            visibility,
            trip_version,
            itinerary_id,
            trip_payload,
            itinerary_version,
            itinerary_payload,
        ) = record
        trip = json.loads(self._protector.decrypt(trip_payload, context="trip.version.snapshot"))
        itinerary = (
            json.loads(
                self._protector.decrypt(itinerary_payload, context="itinerary.version.snapshot")
            )
            if itinerary_payload
            else None
        )
        return {
            "trip_id": trip_id,
            "family_id": family,
            "owner_user_id": owner,
            "visibility": visibility,
            "trip_version": trip_version,
            "itinerary_version": itinerary_version or 0,
            "requirements": trip["requirements"],
            "participants": trip["participants"],
            "current_itinerary": itinerary,
            "current_itinerary_version_id": itinerary_id,
        }

    async def create_run(
        self, run: PlanningRun, actor_user_id: str, request_id: str | None
    ) -> None:
        self.session.add(self._run_row(run, actor_user_id))
        await self._audit(
            "planning.run_started",
            actor_user_id,
            "planning_run",
            run.id,
            request_id,
            {"run_id": run.id, "trip_id": run.trip_id},
        )

    async def succeed(
        self,
        run: PlanningRun,
        proposal: Proposal,
        provider: str,
        model: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> None:
        await self._update_run(run)
        payload = json.dumps(
            {
                "days": proposal.days,
                "warnings": proposal.warnings,
                "usage": {
                    "input_tokens": proposal.usage.input_tokens,
                    "output_tokens": proposal.usage.output_tokens,
                    "cache_hit_tokens": proposal.usage.cache_hit_tokens,
                    "estimated_cost_microusd": proposal.usage.estimated_cost_microusd,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.session.add(
            ProposalRow(
                id=proposal.id,
                run_id=proposal.run_id,
                trip_id=proposal.trip_id,
                status=proposal.status,
                base_itinerary_version=proposal.base_itinerary_version,
                payload_ciphertext=self._protector.encrypt(
                    payload, context="planning.proposal.payload"
                ),
                payload_hash=self._protector.digest(payload, context="planning.proposal.digest"),
                summary_ciphertext=self._protector.encrypt(
                    proposal.summary, context="planning.proposal.summary"
                ),
                rationale_ciphertext=self._protector.encrypt(
                    proposal.rationale, context="planning.proposal.rationale"
                ),
                created_at=proposal.created_at,
                applied_at=None,
            )
        )
        self.session.add(
            ProviderUsageRow(
                id=new_uuid7(),
                run_id=run.id,
                provider=provider,
                model=model,
                operation="itinerary_design",
                input_tokens=proposal.usage.input_tokens,
                output_tokens=proposal.usage.output_tokens,
                cache_hit_tokens=proposal.usage.cache_hit_tokens,
                estimated_cost_microusd=proposal.usage.estimated_cost_microusd,
                success=1,
                created_at=proposal.created_at,
            )
        )
        await self._audit(
            "planning.proposal_created",
            actor_user_id,
            "planning_proposal",
            proposal.id,
            request_id,
            {"run_id": run.id, "trip_id": run.trip_id},
        )

    async def fail(
        self,
        run: PlanningRun,
        usage: ModelUsage | None,
        provider: str,
        model: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> None:
        await self._update_run(run)
        measured = usage or ModelUsage(0, 0, 0, 0)
        self.session.add(
            ProviderUsageRow(
                id=new_uuid7(),
                run_id=run.id,
                provider=provider,
                model=model,
                operation="itinerary_design",
                input_tokens=measured.input_tokens,
                output_tokens=measured.output_tokens,
                cache_hit_tokens=measured.cache_hit_tokens,
                estimated_cost_microusd=measured.estimated_cost_microusd,
                success=0,
                created_at=run.completed_at or run.created_at,
            )
        )
        await self._audit(
            "planning.run_failed",
            actor_user_id,
            "planning_run",
            run.id,
            request_id,
            {"trip_id": run.trip_id},
        )

    async def get_run(self, run_id: str) -> PlanningRun | None:
        row = await self.session.get(PlanningRunRow, run_id)
        return self._run(row) if row else None

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        row = await self.session.get(ProposalRow, proposal_id)
        return self._proposal(row) if row else None

    async def list_proposals(self, trip_id: str) -> tuple[Proposal, ...]:
        rows = await self.session.scalars(
            select(ProposalRow)
            .where(ProposalRow.trip_id == trip_id)
            .order_by(ProposalRow.created_at.desc())
        )
        return tuple(self._proposal(row) for row in rows)

    async def mark_applied(
        self,
        proposal_id: str,
        expected_status: str,
        applied_at: datetime,
        actor_user_id: str,
        request_id: str | None,
    ) -> bool:
        result = cast(
            CursorResult[object],
            await self.session.execute(
                update(ProposalRow)
                .where(ProposalRow.id == proposal_id, ProposalRow.status == expected_status)
                .values(status="applied", applied_at=applied_at)
            ),
        )
        applied = result.rowcount == 1
        if applied:
            await self._audit(
                "planning.proposal_applied",
                actor_user_id,
                "planning_proposal",
                proposal_id,
                request_id,
                {"proposal_id": proposal_id},
            )
        return applied

    def _run_row(self, run: PlanningRun, actor: str) -> PlanningRunRow:
        return PlanningRunRow(
            id=run.id,
            trip_id=run.trip_id,
            status=run.status,
            profile=run.profile,
            current_node=run.current_node,
            base_trip_version=run.base_trip_version,
            base_itinerary_version=run.base_itinerary_version,
            error_ciphertext=self._protector.encrypt(run.error, context="planning.run.error"),
            created_by_user_id=actor,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    async def _update_run(self, run: PlanningRun) -> None:
        await self.session.execute(
            update(PlanningRunRow)
            .where(PlanningRunRow.id == run.id)
            .values(
                status=run.status,
                current_node=run.current_node,
                error_ciphertext=self._protector.encrypt(run.error, context="planning.run.error"),
                completed_at=run.completed_at,
            )
        )

    def _run(self, row: PlanningRunRow) -> PlanningRun:
        return PlanningRun(
            row.id,
            row.trip_id,
            row.status,
            row.profile,
            row.current_node,
            row.base_trip_version,
            row.base_itinerary_version,
            self._protector.decrypt(row.error_ciphertext, context="planning.run.error"),
            row.created_at,
            row.completed_at,
        )

    def _proposal(self, row: ProposalRow) -> Proposal:
        payload = json.loads(
            self._protector.decrypt(row.payload_ciphertext, context="planning.proposal.payload")
        )
        usage = payload["usage"]
        return Proposal(
            row.id,
            row.run_id,
            row.trip_id,
            row.status,
            row.base_itinerary_version,
            self._protector.decrypt(row.summary_ciphertext, context="planning.proposal.summary"),
            self._protector.decrypt(
                row.rationale_ciphertext, context="planning.proposal.rationale"
            ),
            tuple(payload["days"]),
            tuple(payload["warnings"]),
            ModelUsage(**usage),
            row.created_at,
            row.applied_at,
        )

    async def _audit(
        self,
        event: str,
        actor: str,
        subject_type: str,
        subject_id: str,
        request_id: str | None,
        details: dict[str, object],
    ) -> None:
        now = datetime.now().astimezone()
        await self.session.execute(
            text(
                "INSERT INTO audit_events "
                "(id,event_type,actor_user_id,source_type,subject_type,subject_id,"
                "request_id,details_json,created_at) VALUES "
                "(:id,:event,:actor,'user',:subject_type,:subject_id,"
                ":request,:details,:created)"
            ),
            {
                "id": new_uuid7(),
                "event": event,
                "actor": actor,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "request": request_id,
                "details": json.dumps(details),
                "created": now,
            },
        )
