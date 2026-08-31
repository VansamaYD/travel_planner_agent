from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.itinerary.application.service import DayInput, ItemInput
from travel_agent.modules.itinerary.domain.models import ItineraryDay, ItineraryItem, ItineraryPlan
from travel_agent.modules.tools.domain import ToolError

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


class MapPointData(BaseModel):
    logical_id: str
    day_id: str
    day_index: int
    sequence: int
    city: str
    title: str
    place_name: str
    longitude: float | None
    latitude: float | None
    address: str
    map_url: str
    status: Literal["resolved", "unresolved"]


class ItineraryMapData(BaseModel):
    enabled: bool
    js_api_key: str
    js_security_key: str
    points: tuple[MapPointData, ...]
    warnings: tuple[str, ...]


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


@router.get("/map-points")
async def get_itinerary_map_points(
    trip_id: str,
    request: Request,
    day_index: Annotated[int | None, Query(ge=0, le=59)] = None,
) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    plan = await container.itinerary_service.get(session, trip_id)
    selected_days = (
        tuple(enumerate(plan.days))
        if day_index is None
        else tuple((index, day) for index, day in enumerate(plan.days) if index == day_index)
    )
    candidates = [
        (index, sequence, day, item)
        for index, day in selected_days
        for sequence, item in enumerate(day.items)
        if item.place_name or item.title
    ][:30]
    semaphore = asyncio.Semaphore(3)

    async def resolve(candidate: tuple[int, int, ItineraryDay, ItineraryItem]) -> MapPointData:
        day_index, sequence, day, item = candidate
        city = day.city
        place_name = item.place_name or item.title
        map_url = "https://uri.amap.com/search?" + urlencode_map(place_name, city)
        try:
            async with semaphore:
                result = await container.tool_gateway.execute(
                    "place_search", {"query": place_name, "city": city}, session.user.id
                )
            places = result.data.get("places")
            place = places[0] if isinstance(places, list) and places else {}
            if isinstance(place, dict):
                longitude = _float_or_none(place.get("longitude"))
                latitude = _float_or_none(place.get("latitude"))
                if longitude is None or latitude is None:
                    raise ToolError("地点坐标缺失。")
                return MapPointData(
                    logical_id=item.logical_id,
                    day_id=day.id,
                    day_index=day_index,
                    sequence=sequence,
                    city=city,
                    title=item.title,
                    place_name=place_name,
                    longitude=longitude,
                    latitude=latitude,
                    address=str(place.get("address") or ""),
                    map_url=map_url,
                    status="resolved",
                )
        except ToolError:
            pass
        return MapPointData(
            logical_id=item.logical_id,
            day_id=day.id,
            day_index=day_index,
            sequence=sequence,
            city=city,
            title=item.title,
            place_name=place_name,
            longitude=None,
            latitude=None,
            address="",
            map_url=map_url,
            status="unresolved",
        )

    points = tuple(await asyncio.gather(*(resolve(value) for value in candidates)))
    js_key = container.settings.amap_js_api_key
    security_key = container.settings.amap_js_security_key
    data = ItineraryMapData(
        enabled=js_key is not None and bool(js_key.get_secret_value()),
        js_api_key=js_key.get_secret_value() if js_key is not None else "",
        js_security_key=security_key.get_secret_value() if security_key is not None else "",
        points=points,
        warnings=("最多展示前 30 个行程点。",) if len(candidates) == 30 else (),
    )
    return {"data": data, "meta": {"request_id": _request_id(request)}}


def urlencode_map(place_name: str, city: str) -> str:
    return urlencode({"keyword": place_name, "city": city, "src": "travel_planner_agent"})


def _float_or_none(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
