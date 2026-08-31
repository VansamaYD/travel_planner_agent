from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.bootstrap.container import Container
from travel_agent.modules.access.application.errors import AuthenticationRequiredError
from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.conversations.domain import ChatMessage, Conversation

router = APIRouter(prefix="/api/v1", tags=["conversations"])


class ConversationData(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageData(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)


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


def _conversation(value: Conversation) -> ConversationData:
    return ConversationData(
        id=value.id,
        title=value.title,
        created_at=value.created_at.isoformat(),
        updated_at=value.updated_at.isoformat(),
    )


def _message(value: ChatMessage) -> MessageData:
    return MessageData(
        id=value.id, role=value.role, content=value.content, created_at=value.created_at.isoformat()
    )


@router.post("/conversations", status_code=201)
async def create_conversation(
    request: Request, x_csrf_token: Annotated[str | None, Header()] = None
) -> dict[str, object]:
    value = await _container(request).conversation_service.create(
        await _session(request), x_csrf_token
    )
    return {"data": _conversation(value)}


@router.get("/conversations")
async def list_conversations(request: Request) -> dict[str, object]:
    values = await _container(request).conversation_service.list(await _session(request))
    return {"data": [_conversation(value) for value in values]}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request) -> dict[str, object]:
    values = await _container(request).conversation_service.messages(
        await _session(request), conversation_id
    )
    return {"data": [_message(value) for value in values]}


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: SendRequest,
    request: Request,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    events = _container(request).conversation_service.stream_message(
        await _session(request), x_csrf_token, conversation_id, payload.content
    )

    async def body() -> AsyncIterator[str]:
        async for event in events:
            yield f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
