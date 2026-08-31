from __future__ import annotations

import secrets
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.knowledge.domain import ImageAnalysis, PlaceCard

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class UpdatePlaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["attraction", "restaurant", "hotel", "transport_hub", "other"] | None = (
        None
    )
    name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    intro: str | None = Field(default=None, max_length=8000)
    details: dict[str, object] | None = None


class AnalyzeImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str = Field(min_length=8, max_length=8192)
    mode: Literal["auto", "guide_page", "place_photo"] = "auto"


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


def _csrf(session: AuthenticatedSession, supplied: str | None) -> None:
    if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
        raise HTTPException(status_code=403, detail="CSRF 校验失败。")


@router.get("/places")
async def list_places(
    request: Request,
    query: str = Query(default="", max_length=200),
    city: str = Query(default="", max_length=100),
    entity_type: str = Query(default="", max_length=24),
) -> dict[str, object]:
    session = await _session(request)
    values = await _container(request).knowledge_service.list_places(
        session.user.id, query, city, entity_type
    )
    return {"data": [_place(value) for value in values]}


@router.patch("/places/{card_id}")
async def update_place(
    card_id: str,
    payload: UpdatePlaceRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    session = await _session(request)
    _csrf(session, x_csrf_token)
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="没有需要更新的字段。")
    value = await _container(request).knowledge_service.update_place(
        session.user.id, card_id, changes
    )
    if value is None:
        raise HTTPException(status_code=404, detail="地点卡不存在。")
    return {"data": _place(value)}


@router.post("/images/analyze")
async def analyze_image(
    payload: AnalyzeImageRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    session = await _session(request)
    _csrf(session, x_csrf_token)
    value, cache_hit = await _container(request).knowledge_service.analyze_image(
        session.user.id, payload.source_url, payload.mode
    )
    return {"data": _analysis(value), "meta": {"cache_hit": cache_hit}}


def _place(value: PlaceCard) -> dict[str, object]:
    return {
        "id": value.id,
        "entity_type": value.entity_type,
        "name": value.name,
        "city": value.city,
        "address": value.address,
        "intro": value.intro,
        "details": value.details,
        "longitude": value.longitude,
        "latitude": value.latitude,
        "confidence": value.confidence,
        "version": value.version,
        "last_verified_at": _iso(value.last_verified_at),
        "expires_at": _iso(value.expires_at),
        "updated_at": value.updated_at.isoformat(),
    }


def _analysis(value: ImageAnalysis) -> dict[str, object]:
    return {
        "id": value.id,
        "source_url": value.source_url,
        "model_name": value.model_name,
        "prompt_version": value.prompt_version,
        "analysis_mode": value.analysis_mode,
        "status": value.status,
        "result": value.result,
        "created_at": value.created_at.isoformat(),
        "analyzed_at": _iso(value.analyzed_at),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
