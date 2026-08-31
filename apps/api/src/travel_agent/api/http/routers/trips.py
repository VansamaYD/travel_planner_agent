from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.trips.application.service import (
    CreateTripInput,
    RequirementsInput,
    UpdateTripInput,
)
from travel_agent.modules.trips.domain.models import (
    TripDraft,
    TripListItem,
    TripParticipant,
    TripRequirements,
    TripVersion,
)

router = APIRouter(prefix="/api/v1/trips", tags=["trips"])


class MetaResponse(BaseModel):
    request_id: str


class RequirementsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_mode: Literal["form", "chat", "import"] = "form"
    origin: str = Field(default="", max_length=120)
    destinations: tuple[str, ...] = Field(default=(), max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    budget_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    styles: tuple[str, ...] = Field(default=(), max_length=20)
    pace: Literal["leisure", "balanced", "compact", "custom"] = "balanced"
    transportation: tuple[str, ...] = Field(default=(), max_length=20)
    hard_constraints: tuple[str, ...] = Field(default=(), max_length=30)
    soft_preferences: tuple[str, ...] = Field(default=(), max_length=30)
    assumptions: tuple[str, ...] = Field(default=(), max_length=30)
    source_text: str = Field(default="", max_length=8000)
    confirmed: bool = False


class CreateTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family_id: str
    title: str = Field(min_length=1, max_length=80)
    visibility: Literal["private", "family"] = "private"
    requirements: RequirementsPayload
    membership_ids: tuple[str, ...] = Field(default=(), max_length=50)


class UpdateTripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=80)
    visibility: Literal["private", "family"]
    requirements: RequirementsPayload
    membership_ids: tuple[str, ...] = Field(default=(), max_length=50)


class RequirementsData(BaseModel):
    input_mode: str
    origin: str
    destinations: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    budget_cents: int | None
    currency: str
    styles: tuple[str, ...]
    pace: str
    transportation: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]
    assumptions: tuple[str, ...]
    source_text: str
    confirmed: bool


class ParticipantData(BaseModel):
    id: str
    source_membership_id: str | None
    display_name: str
    member_type: str
    birth_year: int | None
    discount_eligibilities: tuple[str, ...]
    dietary_restrictions: tuple[str, ...]
    allergies: tuple[str, ...]
    health_notes: str
    mobility_notes: str
    travel_preferences: tuple[str, ...]
    is_temporary: bool


class TripData(BaseModel):
    id: str
    family_id: str
    owner_user_id: str
    title: str
    status: str
    visibility: str
    version: int
    requirements: RequirementsData
    participants: tuple[ParticipantData, ...]
    warnings: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class TripListItemData(BaseModel):
    id: str
    family_id: str
    owner_user_id: str
    title: str
    status: str
    visibility: str
    version: int
    origin: str
    destinations: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    participant_count: int
    updated_at: datetime


class VersionData(BaseModel):
    id: str
    trip_id: str
    version_no: int
    change_type: str
    summary: str
    created_by_user_id: str
    created_at: datetime
    snapshot: TripData | None


class TripResponse(BaseModel):
    data: TripData
    meta: MetaResponse


class TripListResponse(BaseModel):
    data: tuple[TripListItemData, ...]
    meta: MetaResponse


class VersionListResponse(BaseModel):
    data: tuple[VersionData, ...]
    meta: MetaResponse


class VersionResponse(BaseModel):
    data: VersionData
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


def _requirements_input(value: RequirementsPayload) -> RequirementsInput:
    return RequirementsInput(**value.model_dump())


def _requirements_data(value: TripRequirements) -> RequirementsData:
    return RequirementsData(
        input_mode=value.input_mode.value,
        origin=value.origin,
        destinations=value.destinations,
        start_date=value.start_date,
        end_date=value.end_date,
        budget_cents=value.budget_cents,
        currency=value.currency,
        styles=value.styles,
        pace=value.pace,
        transportation=value.transportation,
        hard_constraints=value.hard_constraints,
        soft_preferences=value.soft_preferences,
        assumptions=value.assumptions,
        source_text=value.source_text,
        confirmed=value.confirmed,
    )


def _participant_data(value: TripParticipant) -> ParticipantData:
    return ParticipantData(
        **{field: getattr(value, field) for field in ParticipantData.model_fields}
    )


def _trip_data(value: TripDraft) -> TripData:
    return TripData(
        id=value.id,
        family_id=value.family_id,
        owner_user_id=value.owner_user_id,
        title=value.title,
        status=value.status.value,
        visibility=value.visibility.value,
        version=value.version,
        requirements=_requirements_data(value.requirements),
        participants=tuple(_participant_data(item) for item in value.participants),
        warnings=value.warnings,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _list_data(value: TripListItem) -> TripListItemData:
    return TripListItemData(
        **{
            **{field: getattr(value, field) for field in TripListItemData.model_fields},
            "status": value.status.value,
            "visibility": value.visibility.value,
        }
    )


def _version_data(value: TripVersion) -> VersionData:
    return VersionData(
        id=value.id,
        trip_id=value.trip_id,
        version_no=value.version_no,
        change_type=value.change_type,
        summary=value.summary,
        created_by_user_id=value.created_by_user_id,
        created_at=value.created_at,
        snapshot=_trip_data(value.snapshot) if value.snapshot else None,
    )


@router.get("", response_model=TripListResponse)
async def list_trips(
    request: Request, family_id: Annotated[str | None, Query()] = None
) -> TripListResponse:
    items = await _container(request).trip_service.list(await _session(request), family_id)
    return TripListResponse(
        data=tuple(_list_data(item) for item in items),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    payload: CreateTripRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> TripResponse:
    result = await _container(request).trip_service.create(
        await _session(request),
        x_csrf_token,
        CreateTripInput(
            family_id=payload.family_id,
            title=payload.title,
            visibility=payload.visibility,
            requirements=_requirements_input(payload.requirements),
            membership_ids=payload.membership_ids,
        ),
        _request_id(request),
    )
    return TripResponse(data=_trip_data(result), meta=MetaResponse(request_id=_request_id(request)))


@router.get("/deleted", response_model=TripListResponse)
async def list_deleted_trips(
    request: Request, family_id: Annotated[str | None, Query()] = None
) -> TripListResponse:
    items = await _container(request).trip_service.deleted(await _session(request), family_id)
    return TripListResponse(
        data=tuple(_list_data(item) for item in items),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(trip_id: str, request: Request) -> TripResponse:
    result = await _container(request).trip_service.get(await _session(request), trip_id)
    return TripResponse(data=_trip_data(result), meta=MetaResponse(request_id=_request_id(request)))


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    await _container(request).trip_service.delete(
        await _session(request), x_csrf_token, trip_id, _request_id(request)
    )


@router.post("/{trip_id}/restore", response_model=TripResponse)
async def restore_trip(
    trip_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> TripResponse:
    result = await _container(request).trip_service.restore(
        await _session(request), x_csrf_token, trip_id, _request_id(request)
    )
    return TripResponse(data=_trip_data(result), meta=MetaResponse(request_id=_request_id(request)))


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: str,
    payload: UpdateTripRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> TripResponse:
    result = await _container(request).trip_service.update(
        await _session(request),
        x_csrf_token,
        trip_id,
        UpdateTripInput(
            expected_version=payload.expected_version,
            title=payload.title,
            visibility=payload.visibility,
            requirements=_requirements_input(payload.requirements),
            membership_ids=payload.membership_ids,
        ),
        _request_id(request),
    )
    return TripResponse(data=_trip_data(result), meta=MetaResponse(request_id=_request_id(request)))


@router.get("/{trip_id}/versions", response_model=VersionListResponse)
async def list_versions(trip_id: str, request: Request) -> VersionListResponse:
    values = await _container(request).trip_service.versions(await _session(request), trip_id)
    return VersionListResponse(
        data=tuple(_version_data(value) for value in values),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.get("/{trip_id}/versions/{version_no}", response_model=VersionResponse)
async def get_version(trip_id: str, version_no: int, request: Request) -> VersionResponse:
    value = await _container(request).trip_service.version(
        await _session(request), trip_id, version_no
    )
    return VersionResponse(
        data=_version_data(value), meta=MetaResponse(request_id=_request_id(request))
    )
