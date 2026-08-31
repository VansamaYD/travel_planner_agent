from datetime import timedelta
from typing import cast

from fastapi import APIRouter, Query, Request

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


async def _session(request: Request) -> AuthenticatedSession:
    container = _container(request)
    value = await container.access_service.authenticate(
        request.cookies.get(container.settings.session_cookie_name)
    )
    if value is None:
        raise AuthenticationRequiredError
    return value


@router.get("")
async def list_tool_capabilities(request: Request) -> dict[str, object]:
    await _session(request)
    return {"data": _container(request).tool_gateway.capabilities()}


@router.get("/usage")
async def get_tool_usage(
    request: Request, days: int = Query(default=30, ge=1, le=180)
) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    values = await container.tool_gateway.usage_summary(
        session.user.id, container.tool_gateway.now() - timedelta(days=days)
    )
    return {"data": values, "period_days": days}
