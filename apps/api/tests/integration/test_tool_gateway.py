from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.security import (
    AesGcmTextProtector,
    resolve_protection_key,
)
from travel_agent.modules.tools.domain import ToolDescriptor, ToolUnavailableError
from travel_agent.modules.tools.models import ExternalCacheRow, ExternalUsageRow, GuideCandidateRow
from travel_agent.modules.tools.runtime import RegisteredTool, ToolGateway
from travel_agent.modules.tools.store import SqlAlchemyToolStore
from travel_agent.shared.infrastructure.db.database import Database


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class FakeProvider:
    name = "fake-map"

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        self.calls += 1
        if self.fail:
            raise ToolUnavailableError("upstream unavailable")
        return {"places": [{"id": "poi-1", "name": args["query"]}]}


async def initialize(client: httpx.AsyncClient) -> tuple[str, str]:
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
    session = response.json()["data"]["session"]
    return session["user"]["id"], session["csrf_token"]


@pytest.mark.asyncio
async def test_tool_gateway_caches_records_usage_and_serves_stale_on_failure(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    owner_id, _ = await initialize(client)
    database = Database.from_settings(settings)
    protector = AesGcmTextProtector(resolve_protection_key(settings))
    provider = FakeProvider()
    clock = MutableClock(datetime(2026, 8, 31, tzinfo=UTC))
    descriptor = ToolDescriptor(
        "place_search",
        "test",
        {"type": "object"},
        provider.name,
        ttl_seconds=10,
        stale_seconds=30,
    )
    gateway = ToolGateway(
        lambda: SqlAlchemyToolStore(database.session_factory, protector),
        clock,
        (RegisteredTool(descriptor, provider, "查询地点"),),
    )

    first = await gateway.execute("place_search", {"query": "拙政园"}, owner_id)
    second = await gateway.execute("place_search", {"query": "  拙政园  "}, owner_id)
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert provider.calls == 1

    clock.value += timedelta(seconds=11)
    provider.fail = True
    stale = await gateway.execute("place_search", {"query": "拙政园"}, owner_id)
    assert stale.cache_status == "stale"
    assert stale.warnings

    usage_response = await client.get("/api/v1/tools/usage?days=30")
    assert usage_response.status_code == 200
    assert sum(item["calls"] for item in usage_response.json()["data"]) == 3

    async with database.session_factory() as session:
        cache = (await session.scalars(select(ExternalCacheRow))).one()
        usage = tuple(await session.scalars(select(ExternalUsageRow)))
    await database.dispose()
    assert "拙政园".encode() not in cache.payload_ciphertext
    assert [item.cache_status for item in usage] == ["miss", "hit", "stale"]


@pytest.mark.asyncio
async def test_guide_results_are_encrypted_and_scoped_to_user(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    owner_id, csrf = await initialize(client)
    database = Database.from_settings(settings)
    protector = AesGcmTextProtector(resolve_protection_key(settings))
    clock = MutableClock(datetime(2026, 8, 31, tzinfo=UTC))

    class GuideProvider:
        name = "xiaohongshu"

        async def execute(
            self, operation: str, args: dict[str, object], owner_user_id: str = ""
        ) -> dict[str, object]:
            return {
                "guides": [
                    {
                        "id": "note-1",
                        "title": "苏州两日攻略",
                        "summary": "早上去园林",
                        "author": "traveler",
                        "url": "https://www.xiaohongshu.com/explore/note-1",
                    }
                ]
            }

    descriptor = ToolDescriptor(
        "guide_search_xhs", "test", {"type": "object"}, "xiaohongshu", 60, 60
    )
    gateway = ToolGateway(
        lambda: SqlAlchemyToolStore(database.session_factory, protector),
        clock,
        (RegisteredTool(descriptor, GuideProvider(), "搜索攻略", private_scope=True),),
    )
    await gateway.execute("guide_search_xhs", {"query": "苏州攻略"}, owner_id)

    listed = await client.get("/api/v1/guides?scope=all")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["title"] == "苏州两日攻略"
    assert listed.json()["data"][0]["url"].startswith("https://www.xiaohongshu.com/")

    async with database.session_factory() as session:
        row = (await session.scalars(select(GuideCandidateRow))).one()
    await database.dispose()
    assert row.owner_user_id == owner_id
    assert "苏州两日攻略".encode() not in row.title_ciphertext

    guide_id = listed.json()["data"][0]["id"]
    updated = await client.patch(
        f"/api/v1/guides/{guide_id}",
        headers={"X-CSRF-Token": csrf},
        json={"city": "苏州", "pinned": True, "user_notes": "优先参考园林路线"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["city"] == "苏州"
    assert updated.json()["data"]["pinned"] is True

    deleted = await client.delete(
        f"/api/v1/guides/{guide_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204
