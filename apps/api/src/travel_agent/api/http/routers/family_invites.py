from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import (
    AuthenticationRequiredError,
    LoginRateLimitedError,
)
from travel_agent.modules.access.domain.models import AuthenticatedSession, FamilyInvite

router = APIRouter(prefix="/api/v1", tags=["family-invites"])


class MetaResponse(BaseModel):
    request_id: str


class CreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "member", "guest"] = "member"
    expires_in_days: int = Field(default=7, ge=1, le=30)


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=20, max_length=64)


class RegisterWithInviteRequest(AcceptInviteRequest):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=256)


class InviteData(BaseModel):
    id: str
    family_id: str
    role: str
    status: str
    created_by_user_id: str
    created_at: datetime
    expires_at: datetime
    accepted_by_user_id: str | None


class InviteListResponse(BaseModel):
    data: tuple[InviteData, ...]
    meta: MetaResponse


class InviteIssueData(BaseModel):
    invite: InviteData
    code: str


class InviteIssueResponse(BaseModel):
    data: InviteIssueData
    meta: MetaResponse


class FamilyIdData(BaseModel):
    family_id: str


class FamilyIdResponse(BaseModel):
    data: FamilyIdData
    meta: MetaResponse


class RegisteredUserData(BaseModel):
    username: str


class RegisteredUserResponse(BaseModel):
    data: RegisteredUserData
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


def _invite_data(invite: FamilyInvite) -> InviteData:
    return InviteData(
        id=invite.id,
        family_id=invite.family_id,
        role=invite.role.value,
        status=invite.status,
        created_by_user_id=invite.created_by_user_id,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        accepted_by_user_id=invite.accepted_by_user_id,
    )


@router.get("/families/{family_id}/invites", response_model=InviteListResponse)
async def list_invites(family_id: str, request: Request) -> InviteListResponse:
    invites = await _container(request).family_invite_service.list_invites(
        await _session(request), family_id
    )
    return InviteListResponse(
        data=tuple(_invite_data(invite) for invite in invites),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post(
    "/families/{family_id}/invites",
    response_model=InviteIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    family_id: str,
    payload: CreateInviteRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> InviteIssueResponse:
    issue = await _container(request).family_invite_service.create_invite(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
        request_id=_request_id(request),
    )
    return InviteIssueResponse(
        data=InviteIssueData(invite=_invite_data(issue.invite), code=issue.code),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.delete("/families/{family_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    family_id: str,
    invite_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    await _container(request).family_invite_service.revoke_invite(
        session=await _session(request),
        csrf_token=x_csrf_token,
        family_id=family_id,
        invite_id=invite_id,
        request_id=_request_id(request),
    )


@router.post("/family-invites/accept", response_model=FamilyIdResponse)
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> FamilyIdResponse:
    family_id = await _container(request).family_invite_service.accept_invite(
        session=await _session(request),
        csrf_token=x_csrf_token,
        code=payload.code,
        request_id=_request_id(request),
    )
    return FamilyIdResponse(
        data=FamilyIdData(family_id=family_id),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post(
    "/family-invites/register",
    response_model=RegisteredUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_with_invite(
    payload: RegisterWithInviteRequest, request: Request
) -> RegisteredUserResponse:
    container = _container(request)
    client_host = request.client.host if request.client else "unknown"
    limiter_key = container.invite_registration_rate_limiter.key(client_host, "invite-registration")
    if not container.invite_registration_rate_limiter.allowed(limiter_key):
        raise LoginRateLimitedError
    container.invite_registration_rate_limiter.record_failure(limiter_key)
    username = await container.family_invite_service.register_with_invite(
        code=payload.code,
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        request_id=_request_id(request),
    )
    return RegisteredUserResponse(
        data=RegisteredUserData(username=username),
        meta=MetaResponse(request_id=_request_id(request)),
    )
