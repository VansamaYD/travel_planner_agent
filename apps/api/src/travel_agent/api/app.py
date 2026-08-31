from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI

from travel_agent.api.http.middleware import RequestIdMiddleware
from travel_agent.api.http.routers.health import router as health_router
from travel_agent.bootstrap.container import Container, build_container
from travel_agent.bootstrap.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.startup()
        try:
            yield
        finally:
            await container.shutdown()

    app = FastAPI(
        title=container.settings.app_name,
        version=container.settings.app_version,
        docs_url="/api/docs" if not container.settings.is_production else None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.container = container
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    return app


def get_container(app: FastAPI) -> Container:
    """Only inbound adapters may access the app-owned composition root."""

    return cast(Container, app.state.container)
