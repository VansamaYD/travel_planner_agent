from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.security import (
    AesGcmTextProtector,
    resolve_protection_key,
)
from travel_agent.modules.knowledge.models import ImageAnalysisRow, PlaceKnowledgeCardRow
from travel_agent.modules.knowledge.service import KnowledgeService
from travel_agent.modules.knowledge.store import SqlAlchemyKnowledgeStore
from travel_agent.shared.infrastructure.db.database import Database


@dataclass
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class FakeVision:
    model_name = "vision-test"
    prompt_version = "prompt-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, source_url: str, mode: str) -> dict[str, object]:
        self.calls += 1
        return {
            "image_kind": "guide_page",
            "suggested_filename": "青岛路线图.jpg",
            "transcription": "栈桥到八大关",
        }


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
    return str(response.json()["data"]["session"]["user"]["id"])


@pytest.mark.asyncio
async def test_place_cards_are_versioned_and_image_analysis_is_deduplicated(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    owner_id = await initialize(client)
    database = Database.from_settings(settings)
    protector = AesGcmTextProtector(resolve_protection_key(settings))
    clock = FixedClock(datetime(2026, 9, 1, tzinfo=UTC))
    vision = FakeVision()
    service = KnowledgeService(
        lambda: SqlAlchemyKnowledgeStore(database.session_factory, protector), vision, clock
    )

    payload = {
        "places": [
            {
                "id": "poi-qingdao-1",
                "name": "栈桥",
                "city": "青岛市",
                "address": "太平路",
                "type": "风景名胜;景点",
                "longitude": 120.32,
                "latitude": 36.06,
                "rating": "4.7",
            }
        ]
    }
    first = await service.capture_place_results(owner_id, payload)
    second = await service.capture_place_results(owner_id, payload)
    assert first[0].id == second[0].id
    assert second[0].version == 1
    assert (await service.find_place(owner_id, "栈桥", "青岛市")).longitude == 120.32
    enriched = await service.upsert_agent_claim(
        owner_id,
        {
            "name": "栈桥",
            "city": "青岛市",
            "entity_type": "attraction",
            "intro": "青岛代表性滨海地标",
            "details": {"reservation": "无需预约"},
            "evidence_source": "guide:test-note",
            "confidence": 0.7,
        },
    )
    assert enriched.id == first[0].id
    assert enriched.version == 2
    assert enriched.details["reservation"] == "无需预约"

    image_url = "https://img.example/qingdao-guide.jpg"
    analyzed, first_hit = await service.analyze_image(owner_id, image_url)
    cached, second_hit = await service.analyze_image(owner_id, image_url)
    assert first_hit is False
    assert second_hit is True
    assert analyzed.id == cached.id
    assert vision.calls == 1

    async with database.session_factory() as session:
        place_count = await session.scalar(select(func.count()).select_from(PlaceKnowledgeCardRow))
        image_rows = tuple(await session.scalars(select(ImageAnalysisRow)))
    await database.dispose()
    assert place_count == 1
    assert len(image_rows) == 1
    assert image_url.encode() not in image_rows[0].source_url_ciphertext
