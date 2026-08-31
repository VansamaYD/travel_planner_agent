from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.tools.domain import GuideCandidate, ToolError

router = APIRouter(prefix="/api/v1/guides", tags=["guides"])


class ImportGuidesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guide_ids: tuple[str, ...] = Field(min_length=1, max_length=10)


class UpdateGuideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, max_length=24000)
    user_notes: str | None = Field(default=None, max_length=8000)
    pinned: bool | None = None


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


def _guide(value: GuideCandidate, now: datetime) -> dict[str, object]:
    return {
        "id": value.id,
        "provider": value.provider,
        "title": value.title,
        "url": value.url,
        "author": value.author,
        "summary": value.summary,
        "city": value.city or "未分类",
        "source_query": value.source_query,
        "status": value.status,
        "pinned": value.pinned,
        "content": value.content,
        "images": list(value.images),
        "comments": list(value.comments),
        "metadata": value.metadata,
        "user_notes": value.user_notes,
        "fetched_at": value.fetched_at.isoformat(),
        "expires_at": value.expires_at.isoformat(),
        "detail_fetched_at": value.detail_fetched_at.isoformat()
        if value.detail_fetched_at
        else None,
        "detail_expires_at": value.detail_expires_at.isoformat()
        if value.detail_expires_at
        else None,
        "stale": bool(value.detail_expires_at and value.detail_expires_at <= now),
    }


@router.get("")
async def list_guides(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    scope: Literal["library", "all"] = "library",
) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    values = await container.tool_gateway.list_guides(
        session.user.id, limit, library_only=scope == "library"
    )
    now = container.tool_gateway.now()
    return {"data": [_guide(value, now) for value in values]}


@router.get("/{guide_id}")
async def get_guide(guide_id: str, request: Request) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    value = await container.tool_gateway.get_guide(session.user.id, guide_id)
    if value is None:
        raise HTTPException(status_code=404, detail="攻略不存在。")
    return {"data": _guide(value, container.tool_gateway.now())}


@router.post("/import/stream")
async def import_guides(
    payload: ImportGuidesRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    container = _container(request)
    session = await _session(request)
    _csrf(session, x_csrf_token)
    guide_ids = tuple(dict.fromkeys(payload.guide_ids))

    async def events() -> AsyncIterator[str]:
        total = len(guide_ids)
        yield _sse("import.started", {"total": total, "label": f"准备下载 {total} 篇攻略"})
        completed = 0
        for index, guide_id in enumerate(guide_ids, start=1):
            yield _sse(
                "guide.started",
                {
                    "guide_id": guide_id,
                    "index": index,
                    "total": total,
                    "label": "正在读取原文与评论",
                },
            )
            try:
                value = await container.tool_gateway.import_guide(session.user.id, guide_id)
                completed += 1
                yield _sse(
                    "guide.completed",
                    {
                        "guide_id": guide_id,
                        "index": index,
                        "total": total,
                        "label": f"《{value.title}》已保存",
                        "guide": _guide(value, container.tool_gateway.now()),
                    },
                )
            except ToolError as error:
                yield _sse(
                    "guide.failed",
                    {
                        "guide_id": guide_id,
                        "index": index,
                        "total": total,
                        "label": str(error) or "详情下载失败",
                    },
                )
        yield _sse(
            "import.completed",
            {
                "completed": completed,
                "failed": total - completed,
                "total": total,
                "label": f"已保存 {completed}/{total} 篇攻略",
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/{guide_id}")
async def update_guide(
    guide_id: str,
    payload: UpdateGuideRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    container = _container(request)
    session = await _session(request)
    _csrf(session, x_csrf_token)
    value = await container.tool_gateway.update_guide(
        session.user.id, guide_id, **payload.model_dump()
    )
    if value is None:
        raise HTTPException(status_code=404, detail="攻略不存在。")
    return {"data": _guide(value, container.tool_gateway.now())}


@router.delete("/{guide_id}", status_code=204)
async def delete_guide(
    guide_id: str,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    container = _container(request)
    session = await _session(request)
    _csrf(session, x_csrf_token)
    if not await container.tool_gateway.delete_guide(session.user.id, guide_id):
        raise HTTPException(status_code=404, detail="攻略不存在。")


def _sse(event: str, payload: dict[str, object]) -> str:
    body = json.dumps({"event": event, **payload}, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"
