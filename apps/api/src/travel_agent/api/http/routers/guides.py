from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Query, Request

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession

router = APIRouter(prefix="/api/v1/guides", tags=["guides"])


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
async def list_cached_guides(
    request: Request, limit: int = Query(default=30, ge=1, le=100)
) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    values = await container.tool_gateway.list_guides(session.user.id, limit)
    now = container.tool_gateway.now()
    return {
        "data": [
            {
                "id": value.id,
                "provider": value.provider,
                "title": value.title,
                "url": value.url,
                "author": value.author,
                "summary": value.summary,
                "fetched_at": value.fetched_at.isoformat(),
                "expires_at": value.expires_at.isoformat(),
                "stale": value.expires_at <= now,
            }
            for value in values
        ]
    }
