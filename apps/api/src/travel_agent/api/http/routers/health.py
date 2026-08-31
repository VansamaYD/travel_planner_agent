from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from travel_agent.bootstrap.container import Container

router = APIRouter(tags=["system"])


class CheckResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    version: str
    checks: tuple[CheckResponse, ...] = ()


def _container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


@router.get("/health/live", response_model=HealthResponse)
async def live(request: Request) -> HealthResponse:
    container = _container(request)
    return HealthResponse(status="ok", version=container.settings.app_version)


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request, response: Response) -> HealthResponse:
    container = _container(request)
    report = await container.health_service.readiness()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ready" if report.ready else "not_ready",
        version=container.settings.app_version,
        checks=tuple(
            CheckResponse(name=check.name, status=check.status, detail=check.detail)
            for check in report.checks
        ),
    )
