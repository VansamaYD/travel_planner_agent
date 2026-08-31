from __future__ import annotations

import secrets
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession, SystemRole
from travel_agent.modules.operations.runtime_config import apply_runtime_config

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class UpdateIntegrationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, str | int | bool | None] = Field(max_length=30)


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


async def _admin_session(request: Request) -> AuthenticatedSession:
    container = _container(request)
    value = await container.access_service.authenticate(
        request.cookies.get(container.settings.session_cookie_name)
    )
    if value is None:
        raise AuthenticationRequiredError
    if value.user.system_role is not SystemRole.ADMIN:
        raise HTTPException(status_code=403, detail="仅系统管理员可以管理外部连接。")
    return value


def _csrf(session: AuthenticatedSession, supplied: str | None) -> None:
    if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
        raise HTTPException(status_code=403, detail="CSRF 校验失败。")


@router.get("/integrations")
async def get_integrations(request: Request) -> dict[str, object]:
    await _admin_session(request)
    container = _container(request)
    return {
        "data": list(container.runtime_config.describe(container.settings)),
        "meta": {"restart_required": False},
    }


@router.patch("/integrations", status_code=status.HTTP_202_ACCEPTED)
async def update_integrations(
    payload: UpdateIntegrationsRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    session = await _admin_session(request)
    _csrf(session, x_csrf_token)
    try:
        container = _container(request)
        container.runtime_config.save(dict(payload.values))
        effective_settings = apply_runtime_config(container.settings, container.runtime_config)
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await container.access_service.record_integration_settings_change(
        session,
        tuple(sorted(payload.values)),
        getattr(request.state, "request_id", None),
    )
    return {
        "data": list(container.runtime_config.describe(effective_settings)),
        "meta": {
            "restart_required": True,
            "message": "配置已加密保存。重启服务后载入新的外部连接。",
        },
    }
