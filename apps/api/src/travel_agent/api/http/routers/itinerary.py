from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.itinerary.application.service import DayInput, ItemInput
from travel_agent.modules.itinerary.domain.models import ItineraryPlan

router = APIRouter(prefix="/api/v1/trips/{trip_id}/itinerary", tags=["itinerary"])


class ItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logical_id: str | None = None
    item_type: Literal[
        "place", "restaurant", "hotel", "rest", "transport", "free_time", "other"
    ] = "place"
    title: str = Field(min_length=1, max_length=120)
    place_name: str = Field(default="", max_length=160)
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    cost_cents: int | None = Field(default=None, ge=0)
    execution_status: Literal[
        "candidate", "planned", "confirmed", "booked", "completed", "skipped", "cancelled"
    ] = "planned"
    notes: str = Field(default="", max_length=1000)
    tags: tuple[str, ...] = Field(default=(), max_length=20)
    transport_to_next: str | None = Field(default=None, max_length=32)
    travel_minutes_to_next: int | None = Field(default=None, ge=0, le=1440)
    travel_cost_cents_to_next: int | None = Field(default=None, ge=0)


class DayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    local_date: date
    city: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=500)
    items: tuple[ItemPayload, ...] = Field(default=(), max_length=40)


class UpdateItineraryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    days: tuple[DayPayload, ...] = Field(min_length=1, max_length=60)


class ItemData(ItemPayload):
    logical_id: str


class DayData(BaseModel):
    id: str
    local_date: date
    city: str
    summary: str
    items: tuple[ItemData, ...]


class ItineraryData(BaseModel):
    id: str
    trip_id: str
    version: int
    days: tuple[DayData, ...]
    currency: str
    estimated_total_cost_cents: int
    warnings: tuple[str, ...]
    created_by_user_id: str
    created_at: datetime


class VersionData(BaseModel):
    id: str
    trip_id: str
    version: int
    change_type: str
    summary: str
    created_by_user_id: str
    created_at: datetime


class MetaResponse(BaseModel):
    request_id: str


class ItineraryResponse(BaseModel):
    data: ItineraryData
    meta: MetaResponse


class VersionListResponse(BaseModel):
    data: tuple[VersionData, ...]
    meta: MetaResponse


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def _request_id(request: Request) -> str:
    return cast(str, request.state.request_id)


async def _session(request: Request) -> AuthenticatedSession:
    container = _container(request)
    session = await container.access_service.authenticate(
        request.cookies.get(container.settings.session_cookie_name)
    )
    if session is None:
        raise AuthenticationRequiredError
    return session


def _data(plan: ItineraryPlan) -> ItineraryData:
    return ItineraryData(
        id=plan.id,
        trip_id=plan.trip_id,
        version=plan.version,
        days=tuple(
            DayData(
                id=day.id,
                local_date=day.local_date,
                city=day.city,
                summary=day.summary,
                items=tuple(
                    ItemData(**{field: getattr(item, field) for field in ItemData.model_fields})
                    for item in day.items
                ),
            )
            for day in plan.days
        ),
        currency=plan.currency,
        estimated_total_cost_cents=plan.estimated_total_cost_cents,
        warnings=plan.warnings,
        created_by_user_id=plan.created_by_user_id,
        created_at=plan.created_at,
    )


def _day_input(day: DayPayload) -> DayInput:
    return DayInput(
        id=day.id,
        local_date=day.local_date,
        city=day.city,
        summary=day.summary,
        items=tuple(ItemInput(**item.model_dump()) for item in day.items),
    )


@router.get("", response_model=ItineraryResponse)
async def get_itinerary(trip_id: str, request: Request) -> ItineraryResponse:
    plan = await _container(request).itinerary_service.get(await _session(request), trip_id)
    return ItineraryResponse(data=_data(plan), meta=MetaResponse(request_id=_request_id(request)))


@router.post("/initialize", response_model=ItineraryResponse, status_code=status.HTTP_201_CREATED)
async def initialize_itinerary(
    trip_id: str, request: Request, x_csrf_token: Annotated[str | None, Header()] = None
) -> ItineraryResponse:
    plan = await _container(request).itinerary_service.initialize(
        await _session(request), x_csrf_token, trip_id, _request_id(request)
    )
    return ItineraryResponse(data=_data(plan), meta=MetaResponse(request_id=_request_id(request)))


@router.put("", response_model=ItineraryResponse)
async def update_itinerary(
    trip_id: str,
    payload: UpdateItineraryRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> ItineraryResponse:
    plan = await _container(request).itinerary_service.update(
        await _session(request),
        x_csrf_token,
        trip_id,
        payload.expected_version,
        tuple(_day_input(day) for day in payload.days),
        _request_id(request),
    )
    return ItineraryResponse(data=_data(plan), meta=MetaResponse(request_id=_request_id(request)))


@router.get("/versions", response_model=VersionListResponse)
async def list_itinerary_versions(trip_id: str, request: Request) -> VersionListResponse:
    versions = await _container(request).itinerary_service.versions(
        await _session(request), trip_id
    )
    return VersionListResponse(
        data=tuple(
            VersionData(**{field: getattr(value, field) for field in VersionData.model_fields})
            for value in versions
        ),
        meta=MetaResponse(request_id=_request_id(request)),
    )
