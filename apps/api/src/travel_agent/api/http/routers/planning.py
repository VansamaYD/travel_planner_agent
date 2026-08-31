from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.itinerary.application.errors import ItineraryNotFoundError
from travel_agent.modules.itinerary.application.service import DayInput, ItemInput
from travel_agent.modules.planning.application.errors import PlanningVersionConflictError
from travel_agent.modules.planning.domain.models import PlanningRun, Proposal

router = APIRouter(prefix="/api/v1", tags=["planning"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal["PLAN_STANDARD", "PLAN_DEEP"] = "PLAN_STANDARD"
    instruction: str = Field(default="", max_length=2000)


class RunData(BaseModel):
    id: str
    trip_id: str
    status: str
    profile: str
    current_node: str
    base_trip_version: int
    base_itinerary_version: int
    error: str
    created_at: datetime
    completed_at: datetime | None


class ProposalData(BaseModel):
    id: str
    run_id: str
    trip_id: str
    status: str
    base_itinerary_version: int
    summary: str
    rationale: str
    days: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    cache_hit_tokens: int
    estimated_cost_microusd: int
    created_at: datetime
    applied_at: datetime | None


class StartData(BaseModel):
    run: RunData
    proposal: ProposalData | None


class Meta(BaseModel):
    request_id: str


class StartResponse(BaseModel):
    data: StartData
    meta: Meta


class RunResponse(BaseModel):
    data: RunData
    meta: Meta


class ProposalResponse(BaseModel):
    data: ProposalData
    meta: Meta


class ProposalListResponse(BaseModel):
    data: tuple[ProposalData, ...]
    meta: Meta


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def _rid(request: Request) -> str:
    return cast(str, request.state.request_id)


async def _session(request: Request) -> AuthenticatedSession:
    container = _container(request)
    value = await container.access_service.authenticate(
        request.cookies.get(container.settings.session_cookie_name)
    )
    if value is None:
        raise AuthenticationRequiredError
    return value


def _run(value: PlanningRun) -> RunData:
    return RunData(**{field: getattr(value, field) for field in RunData.model_fields})


def _proposal(value: Proposal) -> ProposalData:
    return ProposalData(
        id=value.id,
        run_id=value.run_id,
        trip_id=value.trip_id,
        status=value.status,
        base_itinerary_version=value.base_itinerary_version,
        summary=value.summary,
        rationale=value.rationale,
        days=value.days,
        warnings=value.warnings,
        input_tokens=value.usage.input_tokens,
        output_tokens=value.usage.output_tokens,
        cache_hit_tokens=value.usage.cache_hit_tokens,
        estimated_cost_microusd=value.usage.estimated_cost_microusd,
        created_at=value.created_at,
        applied_at=value.applied_at,
    )


@router.post("/trips/{trip_id}/planning-runs", response_model=StartResponse)
async def start_run(
    trip_id: str,
    payload: StartRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> StartResponse:
    run, proposal = await _container(request).planning_service.start(
        await _session(request),
        x_csrf_token,
        trip_id,
        payload.profile,
        payload.instruction,
        _rid(request),
    )
    return StartResponse(
        data=StartData(run=_run(run), proposal=_proposal(proposal) if proposal else None),
        meta=Meta(request_id=_rid(request)),
    )


@router.get("/planning-runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    value = await _container(request).planning_service.get_run(await _session(request), run_id)
    return RunResponse(data=_run(value), meta=Meta(request_id=_rid(request)))


@router.get("/trips/{trip_id}/proposals", response_model=ProposalListResponse)
async def list_proposals(trip_id: str, request: Request) -> ProposalListResponse:
    values = await _container(request).planning_service.proposals(await _session(request), trip_id)
    return ProposalListResponse(
        data=tuple(_proposal(value) for value in values), meta=Meta(request_id=_rid(request))
    )


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(proposal_id: str, request: Request) -> ProposalResponse:
    value = await _container(request).planning_service.proposal(
        await _session(request), proposal_id
    )
    return ProposalResponse(data=_proposal(value), meta=Meta(request_id=_rid(request)))


def _days(value: Proposal) -> tuple[DayInput, ...]:
    def items(day: dict[str, object]) -> tuple[ItemInput, ...]:
        raw = day.get("items", [])
        if not isinstance(raw, list):
            return ()
        return tuple(ItemInput(**item) for item in raw if isinstance(item, dict))

    return tuple(
        DayInput(
            id=None,
            local_date=date.fromisoformat(str(day["local_date"])),
            city=str(day["city"]),
            summary=str(day.get("summary", "")),
            items=items(day),
        )
        for day in value.days
    )


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalResponse)
async def apply_proposal(
    proposal_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> ProposalResponse:
    session, container = await _session(request), _container(request)
    proposal = await container.planning_service.proposal(session, proposal_id)
    if proposal.status != "pending":
        raise PlanningVersionConflictError
    try:
        current = await container.itinerary_service.get(session, proposal.trip_id)
    except ItineraryNotFoundError:
        current = await container.itinerary_service.initialize(
            session, x_csrf_token, proposal.trip_id, _rid(request)
        )
    if proposal.base_itinerary_version not in {0, current.version}:
        raise PlanningVersionConflictError
    await container.itinerary_service.update(
        session, x_csrf_token, proposal.trip_id, current.version, _days(proposal), _rid(request)
    )
    await container.planning_service.mark_applied(session, x_csrf_token, proposal_id, _rid(request))
    updated = await container.planning_service.proposal(session, proposal_id)
    return ProposalResponse(data=_proposal(updated), meta=Meta(request_id=_rid(request)))
