from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.application.member_service import ProfileInput
from travel_agent.modules.access.domain.models import (
    AuthenticatedSession,
    FamilyMember,
    TravelerProfile,
)

router = APIRouter(prefix="/api/v1/families/{family_id}/members", tags=["family-members"])


class MetaResponse(BaseModel):
    request_id: str


class ProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(default="", max_length=80)
    member_type: Literal["adult", "child", "senior", "other"] = "adult"
    birth_year: int | None = None
    discount_eligibilities: tuple[str, ...] = Field(default=(), max_length=30)
    dietary_restrictions: tuple[str, ...] = Field(default=(), max_length=30)
    allergies: tuple[str, ...] = Field(default=(), max_length=30)
    health_notes: str = Field(default="", max_length=500)
    mobility_notes: str = Field(default="", max_length=500)
    travel_preferences: tuple[str, ...] = Field(default=(), max_length=30)
    sensitive_visibility: Literal["family", "private"] = "family"


class CreateMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    role: Literal["admin", "member", "guest"] = "member"
    profile: ProfilePayload = Field(default_factory=ProfilePayload)


class UpdateProfileRequest(ProfilePayload):
    expected_version: int = Field(ge=0)


class UpdateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "member", "guest"]


class ProfileData(BaseModel):
    nickname: str
    member_type: str
    birth_year: int | None
    discount_eligibilities: tuple[str, ...]
    dietary_restrictions: tuple[str, ...]
    allergies: tuple[str, ...]
    health_notes: str
    mobility_notes: str
    travel_preferences: tuple[str, ...]
    sensitive_visibility: str
    version: int


class MemberData(BaseModel):
    membership_id: str
    user_id: str
    username: str
    email: str | None
    display_name: str
    role: str
    joined_at: datetime
    profile: ProfileData


class MemberListResponse(BaseModel):
    data: tuple[MemberData, ...]
    meta: MetaResponse


class ResourceIdData(BaseModel):
    id: str


class ResourceIdResponse(BaseModel):
    data: ResourceIdData
    meta: MetaResponse


class ProfileResponse(BaseModel):
    data: ProfileData
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


def _profile_input(payload: ProfilePayload) -> ProfileInput:
    return ProfileInput(
        nickname=payload.nickname,
        member_type=payload.member_type,
        birth_year=payload.birth_year,
        discount_eligibilities=payload.discount_eligibilities,
        dietary_restrictions=payload.dietary_restrictions,
        allergies=payload.allergies,
        health_notes=payload.health_notes,
        mobility_notes=payload.mobility_notes,
        travel_preferences=payload.travel_preferences,
        sensitive_visibility=payload.sensitive_visibility,
    )


def _profile_data(profile: TravelerProfile) -> ProfileData:
    return ProfileData(
        nickname=profile.nickname,
        member_type=profile.member_type.value,
        birth_year=profile.birth_year,
        discount_eligibilities=profile.discount_eligibilities,
        dietary_restrictions=profile.dietary_restrictions,
        allergies=profile.allergies,
        health_notes=profile.health_notes,
        mobility_notes=profile.mobility_notes,
        travel_preferences=profile.travel_preferences,
        sensitive_visibility=profile.sensitive_visibility.value,
        version=profile.version,
    )


def _member_data(member: FamilyMember) -> MemberData:
    return MemberData(
        membership_id=member.membership_id,
        user_id=member.user.id,
        username=member.user.username,
        email=member.user.email,
        display_name=member.user.display_name,
        role=member.role.value,
        joined_at=member.joined_at,
        profile=_profile_data(member.profile),
    )


@router.get("", response_model=MemberListResponse)
async def list_members(family_id: str, request: Request) -> MemberListResponse:
    members = await _container(request).family_member_service.list_members(
        await _session(request), family_id
    )
    return MemberListResponse(
        data=tuple(_member_data(member) for member in members),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post("", response_model=ResourceIdResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    family_id: str,
    payload: CreateMemberRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> ResourceIdResponse:
    membership_id = await _container(request).family_member_service.create_member(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        role=payload.role,
        profile_input=_profile_input(payload.profile),
        request_id=_request_id(request),
    )
    return ResourceIdResponse(
        data=ResourceIdData(id=membership_id),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.put("/{membership_id}/profile", response_model=ProfileResponse)
async def update_profile(
    family_id: str,
    membership_id: str,
    payload: UpdateProfileRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> ProfileResponse:
    profile = await _container(request).family_member_service.update_profile(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        membership_id=membership_id,
        expected_version=payload.expected_version,
        profile_input=_profile_input(payload),
        request_id=_request_id(request),
    )
    return ProfileResponse(
        data=_profile_data(profile), meta=MetaResponse(request_id=_request_id(request))
    )


@router.patch("/{membership_id}/role", status_code=status.HTTP_204_NO_CONTENT)
async def change_role(
    family_id: str,
    membership_id: str,
    payload: UpdateRoleRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    await _container(request).family_member_service.change_role(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        membership_id=membership_id,
        role=payload.role,
        request_id=_request_id(request),
    )


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    family_id: str,
    membership_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    await _container(request).family_member_service.remove_member(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        membership_id=membership_id,
        request_id=_request_id(request),
    )
