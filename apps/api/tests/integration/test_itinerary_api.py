import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.itinerary.infrastructure.models import (
    ItineraryDayRow,
    ItineraryItemRow,
    ItineraryVersionRow,
)
from travel_agent.shared.infrastructure.db.database import Database


async def create_trip(client: httpx.AsyncClient) -> tuple[str, str]:
    initialized = await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "owner",
            "email": None,
            "display_name": "计划创建者",
            "password": "correct horse battery staple",
            "family_name": "旅行家庭",
        },
    )
    session = initialized.json()["data"]["session"]
    family_id = session["families"][0]["id"]
    created = await client.post(
        "/api/v1/trips",
        headers={"X-CSRF-Token": session["csrf_token"]},
        json={
            "family_id": family_id,
            "title": "苏州两日计划",
            "visibility": "private",
            "membership_ids": [],
            "requirements": {
                "origin": "上海",
                "destinations": ["苏州"],
                "start_date": "2026-10-02",
                "end_date": "2026-10-03",
                "confirmed": True,
            },
        },
    )
    return created.json()["data"]["id"], session["csrf_token"]


@pytest.mark.asyncio
async def test_itinerary_initialization_editing_and_versions(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    trip_id, csrf = await create_trip(client)
    missing = await client.get(f"/api/v1/trips/{trip_id}/itinerary")
    assert missing.status_code == 404

    initialized = await client.post(
        f"/api/v1/trips/{trip_id}/itinerary/initialize",
        headers={"X-CSRF-Token": csrf},
    )
    assert initialized.status_code == 201, initialized.text
    plan = initialized.json()["data"]
    assert plan["version"] == 1
    assert [day["local_date"] for day in plan["days"]] == ["2026-10-02", "2026-10-03"]

    days = plan["days"]
    days[0]["summary"] = "园林与古城步行"
    days[0]["items"] = [
        {
            "logical_id": None,
            "item_type": "place",
            "title": "游览拙政园",
            "place_name": "拙政园",
            "start_time": "09:00",
            "end_time": "11:00",
            "cost_cents": 8000,
            "execution_status": "planned",
            "notes": "票价需要联网复核",
            "tags": ["must_visit"],
            "transport_to_next": "步行",
            "travel_minutes_to_next": 15,
            "travel_cost_cents_to_next": 0,
        },
        {
            "logical_id": None,
            "item_type": "restaurant",
            "title": "午餐",
            "place_name": "待选苏帮菜",
            "start_time": "11:30",
            "end_time": "13:00",
            "cost_cents": 15000,
            "execution_status": "candidate",
            "notes": "",
            "tags": ["ai_recommended"],
            "transport_to_next": None,
            "travel_minutes_to_next": None,
            "travel_cost_cents_to_next": None,
        },
    ]
    updated = await client.put(
        f"/api/v1/trips/{trip_id}/itinerary",
        headers={"X-CSRF-Token": csrf},
        json={"expected_version": 1, "days": days},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["version"] == 2
    assert updated.json()["data"]["estimated_total_cost_cents"] == 23000

    stale = await client.put(
        f"/api/v1/trips/{trip_id}/itinerary",
        headers={"X-CSRF-Token": csrf},
        json={"expected_version": 1, "days": days},
    )
    assert stale.status_code == 409
    versions = await client.get(f"/api/v1/trips/{trip_id}/itinerary/versions")
    assert [value["version"] for value in versions.json()["data"]] == [2, 1]

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        version_rows = tuple(await session.scalars(select(ItineraryVersionRow)))
        day_count = await session.scalar(select(func.count()).select_from(ItineraryDayRow))
        item_count = await session.scalar(select(func.count()).select_from(ItineraryItemRow))
    await database.dispose()
    assert len(version_rows) == 2
    assert all("拙政园".encode() not in row.snapshot_ciphertext for row in version_rows)
    assert day_count == 4
    assert item_count == 2
