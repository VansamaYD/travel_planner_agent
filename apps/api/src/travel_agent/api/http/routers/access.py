from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LoginRateLimitedError,
)
from travel_agent.modules.access.application.service import SessionIssue
from travel_agent.modules.access.domain.models import AuthenticatedSession

router = APIRouter(prefix="/api/v1", tags=["access"])


class MetaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str


class SetupStatusData(BaseModel):
    initialized: bool


class SetupStatusResponse(BaseModel):
    data: SetupStatusData
    meta: MetaResponse


class InitializeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    family_name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class FamilyData(BaseModel):
    id: str
    name: str
    role: str


class UserData(BaseModel):
    id: str
    username: str
    email: str | None
    display_name: str
    system_role: str


class SessionData(BaseModel):
    user: UserData
    csrf_token: str
    expires_at: datetime
    families: tuple[FamilyData, ...]


class SessionResponse(BaseModel):
    data: SessionData
    meta: MetaResponse


class InitializeData(BaseModel):
    recovery_code: str
    session: SessionData


class InitializeResponse(BaseModel):
    data: InitializeData
    meta: MetaResponse


class FamilyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class FamilyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class ResourceIdData(BaseModel):
    id: str


class ResourceIdResponse(BaseModel):
    data: ResourceIdData
    meta: MetaResponse


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def _request_id(request: Request) -> str:
    return cast(str, request.state.request_id)


async def _current_session(request: Request) -> AuthenticatedSession:
    cookie_name = _container(request).settings.session_cookie_name
    cookie_token = request.cookies.get(cookie_name)
    session = await _container(request).access_service.authenticate(cookie_token)
    if session is None:
        raise AuthenticationRequiredError
    return session


def _session_data(session: AuthenticatedSession) -> SessionData:
    return SessionData(
        user=UserData(
            id=session.user.id,
            username=session.user.username,
            email=session.user.email,
            display_name=session.user.display_name,
            system_role=session.user.system_role.value,
        ),
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
        families=tuple(
            FamilyData(id=family.id, name=family.name, role=family.role.value)
            for family in session.families
        ),
    )


def _set_session_cookie(response: Response, request: Request, issue: SessionIssue) -> None:
    settings = _container(request).settings
    max_age = settings.session_lifetime_days * 24 * 60 * 60
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue.cookie_token,
        max_age=max_age,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


@router.get("/setup/status", response_model=SetupStatusResponse)
async def setup_status(request: Request) -> SetupStatusResponse:
    initialized = await _container(request).access_service.setup_status()
    return SetupStatusResponse(
        data=SetupStatusData(initialized=initialized),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post(
    "/setup/initialize",
    response_model=InitializeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initialize(
    payload: InitializeRequest, request: Request, response: Response
) -> InitializeResponse:
    result = await _container(request).access_service.initialize(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        family_name=payload.family_name,
        request_id=_request_id(request),
    )
    _set_session_cookie(response, request, result.session_issue)
    return InitializeResponse(
        data=InitializeData(
            recovery_code=result.recovery_code,
            session=_session_data(result.session_issue.session),
        ),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.post("/auth/login", response_model=SessionResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
    container = _container(request)
    client_host = request.client.host if request.client else "unknown"
    limiter_key = container.login_rate_limiter.key(client_host, payload.login)
    if not container.login_rate_limiter.allowed(limiter_key):
        raise LoginRateLimitedError
    try:
        issue = await container.access_service.login(
            login=payload.login,
            password=payload.password,
            request_id=_request_id(request),
        )
    except InvalidCredentialsError:
        container.login_rate_limiter.record_failure(limiter_key)
        raise
    container.login_rate_limiter.reset(limiter_key)
    _set_session_cookie(response, request, issue)
    return SessionResponse(
        data=_session_data(issue.session),
        meta=MetaResponse(request_id=_request_id(request)),
    )


@router.get("/auth/session", response_model=SessionResponse)
async def auth_session(request: Request) -> SessionResponse:
    session = await _current_session(request)
    return SessionResponse(
        data=_session_data(session), meta=MetaResponse(request_id=_request_id(request))
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    session = await _current_session(request)
    await _container(request).access_service.logout(session, x_csrf_token, _request_id(request))
    response.delete_cookie(_container(request).settings.session_cookie_name, path="/")


@router.get("/families")
async def list_families(request: Request) -> dict[str, Any]:
    session = await _current_session(request)
    return {
        "data": [family.model_dump() for family in _session_data(session).families],
        "meta": {"request_id": _request_id(request)},
    }


@router.post("/families", response_model=ResourceIdResponse, status_code=status.HTTP_201_CREATED)
async def create_family(
    payload: FamilyCreateRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> ResourceIdResponse:
    session = await _current_session(request)
    family_id = await _container(request).access_service.create_family(
        session, x_csrf_token, payload.name, _request_id(request)
    )
    return ResourceIdResponse(
        data=ResourceIdData(id=family_id), meta=MetaResponse(request_id=_request_id(request))
    )


@router.patch("/families/{family_id}", response_model=SessionResponse)
async def rename_family(
    family_id: str,
    payload: FamilyUpdateRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> SessionResponse:
    session = await _container(request).access_service.rename_family(
        await _current_session(request),
        x_csrf_token,
        family_id,
        payload.name,
        _request_id(request),
    )
    return SessionResponse(
        data=_session_data(session), meta=MetaResponse(request_id=_request_id(request))
    )
