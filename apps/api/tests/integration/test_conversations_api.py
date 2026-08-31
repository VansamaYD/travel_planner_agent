from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.conversations.domain import ModelStreamEvent
from travel_agent.modules.conversations.models import (
    AgentRunEventRow,
    AgentRunRow,
    ConversationMessageRow,
)
from travel_agent.modules.tools.domain import ToolResult
from travel_agent.shared.infrastructure.db.database import Database


class FakeChatProvider:
    async def stream_turn(
        self,
        messages: tuple[dict[str, object], ...],
        tools: tuple[dict[str, object], ...],
    ) -> AsyncIterator[ModelStreamEvent]:
        assert messages[-1] == {"role": "user", "content": "帮我规划苏州两日游"}
        yield ModelStreamEvent("text", text="可以，")  # noqa: RUF001
        yield ModelStreamEvent("text", text="先确认日期和人数。")


class ToolCallingProvider:
    async def stream_turn(
        self,
        messages: tuple[dict[str, object], ...],
        tools: tuple[dict[str, object], ...],
    ) -> AsyncIterator[ModelStreamEvent]:
        if messages[-1]["role"] == "tool":
            yield ModelStreamEvent("text", text="拙政园地址已经通过高德查询。")
            return
        yield ModelStreamEvent(
            "tool_call",
            tool_call_id="call-1",
            tool_name="place_search",
            tool_arguments='{"query":"拙政园","city":"苏州"}',
        )


class FakeToolRuntime:
    def model_descriptors(self) -> tuple[dict[str, object], ...]:
        return ({"type": "function", "function": {"name": "place_search"}},)

    def label(self, name: str) -> str:
        return "查询高德地点"

    async def execute(self, name: str, args: dict[str, object], owner_user_id: str) -> ToolResult:
        now = datetime.now(UTC)
        return ToolResult(
            {"places": [{"name": "拙政园", "address": "姑苏区东北街"}]},
            "amap",
            name,
            now,
            now + timedelta(days=1),
            "miss",
        )


class OverlappingGuideProvider:
    async def stream_turn(
        self,
        messages: tuple[dict[str, object], ...],
        tools: tuple[dict[str, object], ...],
    ) -> AsyncIterator[ModelStreamEvent]:
        if messages[-1]["role"] == "tool":
            yield ModelStreamEvent("text", text="已整理去重后的青岛攻略候选。")
            return
        for call_id, query in (
            ("guide-1", "青岛四天三夜"),
            ("guide-2", "青岛四天三夜"),
            ("guide-3", "青岛避人流"),
        ):
            yield ModelStreamEvent(
                "tool_call",
                tool_call_id=call_id,
                tool_name="guide_search_xhs",
                tool_arguments=f'{{"query":"{query}"}}',
            )


class OverlappingGuideRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def model_descriptors(self) -> tuple[dict[str, object], ...]:
        return ({"type": "function", "function": {"name": "guide_search_xhs"}},)

    def label(self, name: str) -> str:
        return "搜索小红书攻略"

    async def execute(self, name: str, args: dict[str, object], owner_user_id: str) -> ToolResult:
        self.calls += 1
        now = datetime.now(UTC)
        first = {
            "candidate_id": "guide-a",
            "title": "青岛四日路线",
            "author": "甲",
            "summary": "经典路线",
            "url": "https://example.com/a",
            "status": "discovered",
        }
        overlap = {
            "candidate_id": "guide-b",
            "title": "青岛避坑攻略",
            "author": "乙",
            "summary": "多关键词共同命中",
            "url": "https://example.com/b",
            "status": "discovered",
        }
        last = {
            "candidate_id": "guide-c",
            "title": "青岛慢游攻略",
            "author": "丙",
            "summary": "避开人流",
            "url": "https://example.com/c",
            "status": "discovered",
        }
        guides = [first, overlap] if args["query"] == "青岛四天三夜" else [overlap, last]
        return ToolResult(
            {"guides": guides},
            "xiaohongshu",
            name,
            now,
            now + timedelta(hours=6),
            "miss",
        )


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


@pytest.mark.asyncio
async def test_conversation_can_be_deleted_with_its_history(client: httpx.AsyncClient) -> None:
    csrf = await initialize(client)
    created = await client.post("/api/v1/conversations", headers={"X-CSRF-Token": csrf})
    conversation_id = created.json()["data"]["id"]

    rejected = await client.delete(f"/api/v1/conversations/{conversation_id}")
    assert rejected.status_code == 403
    deleted = await client.delete(
        f"/api/v1/conversations/{conversation_id}", headers={"X-CSRF-Token": csrf}
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/conversations")).json()["data"] == []


@pytest.mark.asyncio
async def test_conversation_stream_exposes_auditable_tool_progress(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    app.state.container.conversation_service._provider = ToolCallingProvider()
    app.state.container.conversation_service._tools = FakeToolRuntime()
    csrf = await initialize(client)
    created = await client.post("/api/v1/conversations", headers={"X-CSRF-Token": csrf})
    conversation_id = created.json()["data"]["id"]
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers={"X-CSRF-Token": csrf},
        json={"content": "查一下拙政园地址"},
    )
    assert "event: tool.started" in response.text
    assert "event: tool.completed" in response.text
    assert "已联网查询" in response.text
    messages = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert messages.json()["data"][-1]["content"] == "拙政园地址已经通过高德查询。"


@pytest.mark.asyncio
async def test_guide_searches_reuse_exact_calls_and_emit_one_ranked_artifact(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    runtime = OverlappingGuideRuntime()
    app.state.container.conversation_service._provider = OverlappingGuideProvider()
    app.state.container.conversation_service._tools = runtime
    csrf = await initialize(client)
    created = await client.post("/api/v1/conversations", headers={"X-CSRF-Token": csrf})
    conversation_id = created.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers={"X-CSRF-Token": csrf},
        json={"content": "请找两篇青岛攻略"},
    )

    assert response.status_code == 200
    assert runtime.calls == 2
    assert response.text.count("event: artifact.guides") == 1
    assert "复用本轮结果" in response.text
    messages = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    artifacts = messages.json()["data"][-1]["artifacts"]
    assert len(artifacts) == 1
    assert [guide["candidate_id"] for guide in artifacts[0]["guides"]] == [
        "guide-b",
        "guide-a",
    ]
