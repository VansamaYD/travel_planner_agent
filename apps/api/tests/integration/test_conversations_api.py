from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.conversations.models import (
    AgentRunEventRow,
    AgentRunRow,
    ConversationMessageRow,
)
from travel_agent.shared.infrastructure.db.database import Database


class FakeChatProvider:
    async def stream(self, messages: tuple[tuple[str, str], ...]) -> AsyncIterator[str]:
        assert messages[-1] == ("user", "帮我规划苏州两日游")
        yield "可以，"  # noqa: RUF001
        yield "先确认日期和人数。"


async def initialize(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "owner",
            "email": None,
            "display_name": "旅行者",
            "password": "correct horse battery staple",
            "family_name": "旅行家庭",
        },
    )
    return response.json()["data"]["session"]["csrf_token"]


@pytest.mark.asyncio
async def test_streaming_conversation_is_persisted_and_encrypted(
    client: httpx.AsyncClient, app: FastAPI, settings: Settings
) -> None:
    app.state.container.conversation_service._provider = FakeChatProvider()
    csrf = await initialize(client)
    created = await client.post("/api/v1/conversations", headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201
    conversation_id = created.json()["data"]["id"]

    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers={"X-CSRF-Token": csrf},
        json={"content": "帮我规划苏州两日游"},
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: run.started" in body
    assert "event: node.started" in body
    assert body.count("event: assistant.delta") == 2
    assert "event: run.completed" in body

    listed = await client.get("/api/v1/conversations")
    assert listed.json()["data"][0]["title"] == "帮我规划苏州两日游"
    messages = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert [(item["role"], item["content"]) for item in messages.json()["data"]] == [
        ("user", "帮我规划苏州两日游"),
        ("assistant", "可以，先确认日期和人数。"),  # noqa: RUF001
    ]

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        message_rows = tuple(await session.scalars(select(ConversationMessageRow)))
        event_rows = tuple(await session.scalars(select(AgentRunEventRow)))
        succeeded = await session.scalar(
            select(func.count()).select_from(AgentRunRow).where(AgentRunRow.status == "succeeded")
        )
    await database.dispose()
    assert len(message_rows) == 2
    assert "苏州".encode() not in message_rows[0].content_ciphertext
    assert [row.event_type for row in event_rows] == [
        "run.started",
        "node.started",
        "node.started",
        "run.completed",
    ]
    assert succeeded == 1


@pytest.mark.asyncio
async def test_conversation_mutations_require_csrf(client: httpx.AsyncClient) -> None:
    await initialize(client)
    response = await client.post("/api/v1/conversations")
    assert response.status_code == 403
    assert response.json()["code"] == "conversation_permission_denied"
