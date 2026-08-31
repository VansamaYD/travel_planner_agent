from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI

from travel_agent.api.http.middleware import RequestIdMiddleware
from travel_agent.api.http.problems import (
    access_error_handler,
    conversation_error_handler,
    itinerary_error_handler,
    knowledge_error_handler,
    planning_error_handler,
    trip_error_handler,
)
from travel_agent.api.http.routers.access import router as access_router
from travel_agent.api.http.routers.conversations import router as conversations_router
from travel_agent.api.http.routers.family_invites import router as family_invites_router
from travel_agent.api.http.routers.family_members import router as family_members_router
from travel_agent.api.http.routers.guides import router as guides_router
from travel_agent.api.http.routers.health import router as health_router
from travel_agent.api.http.routers.itinerary import router as itinerary_router
from travel_agent.api.http.routers.knowledge import router as knowledge_router
from travel_agent.api.http.routers.planning import router as planning_router
from travel_agent.api.http.routers.tools import router as tools_router
from travel_agent.api.http.routers.trips import router as trips_router
from travel_agent.bootstrap.container import Container, build_container
from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.application.errors import AccessError
from travel_agent.modules.conversations.service import ConversationError
from travel_agent.modules.itinerary.application.errors import ItineraryError
from travel_agent.modules.knowledge.domain import KnowledgeError
from travel_agent.modules.planning.application.errors import PlanningError
from travel_agent.modules.trips.application.errors import TripError


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
    app.add_exception_handler(AccessError, access_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TripError, trip_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ItineraryError, itinerary_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PlanningError, planning_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConversationError, conversation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(KnowledgeError, knowledge_error_handler)  # type: ignore[arg-type]
    app.include_router(health_router)
    app.include_router(access_router)
    app.include_router(conversations_router)
    app.include_router(guides_router)
    app.include_router(tools_router)
    app.include_router(family_members_router)
    app.include_router(family_invites_router)
    app.include_router(trips_router)
    app.include_router(itinerary_router)
    app.include_router(knowledge_router)
    app.include_router(planning_router)
    return app


def get_container(app: FastAPI) -> Container:
    """Only inbound adapters may access the app-owned composition root."""

    return cast(Container, app.state.container)
