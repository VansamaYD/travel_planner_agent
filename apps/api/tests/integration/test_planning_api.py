from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.itinerary.infrastructure.models import ItineraryVersionRow
from travel_agent.modules.planning.domain.models import ModelUsage
from travel_agent.modules.planning.infrastructure.models import (
    PlanningRunRow,
    ProposalRow,
    ProviderUsageRow,
)
from travel_agent.shared.infrastructure.db.database import Database


@dataclass(frozen=True, slots=True)
class FakeResult:
    days: tuple[dict[str, object], ...]
    summary: str
    rationale: str
    warnings: tuple[str, ...]
    usage: ModelUsage


class FakeProvider:
    async def generate_itinerary(self, context: dict[str, object]) -> FakeResult:
        assert set(context) == {
            "requirements",
            "participants",
            "current_itinerary",
            "instruction",
            "profile",
        }
        return FakeResult(
            days=(
                {
                    "local_date": "2026-10-02",
                    "city": "苏州",
                    "summary": "园林与古城",
                    "items": [
                        {
                            "logical_id": None,
                            "item_type": "place",
                            "title": "游览拙政园",
                            "place_name": "拙政园",
                            "start_time": "09:00",
                            "end_time": "11:00",
                            "cost_cents": 8000,
                            "execution_status": "candidate",
                            "notes": "门票和营业时间待核验",
                            "tags": ["must_visit"],
                            "transport_to_next": "步行",
                            "travel_minutes_to_next": 15,
                            "travel_cost_cents_to_next": 0,
                        }
                    ],
                },
                {
                    "local_date": "2026-10-03",
                    "city": "苏州",
                    "summary": "博物馆与河畔",
                    "items": [],
                },
            ),
            summary="苏州两日候选计划",
            rationale="先密后疏，减少折返。",  # noqa: RUF001
            warnings=("价格、营业时间和路线尚未联网核验。",),
            usage=ModelUsage(1200, 600, 200, 980),
        )


async def create_trip(client: httpx.AsyncClient, *, confirmed: bool = True) -> tuple[str, str]:
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
    created = await client.post(
        "/api/v1/trips",
        headers={"X-CSRF-Token": session["csrf_token"]},
        json={
            "family_id": session["families"][0]["id"],
            "title": "苏州两日计划",
            "visibility": "private",
            "membership_ids": [],
            "requirements": {
                "origin": "上海",
                "destinations": ["苏州"],
                "start_date": "2026-10-02",
                "end_date": "2026-10-03",
                "confirmed": confirmed,
            },
        },
    )
    return created.json()["data"]["id"], session["csrf_token"]


@pytest.mark.asyncio
async def test_planning_proposal_requires_confirmation_before_itinerary_update(
    client: httpx.AsyncClient, app: FastAPI, settings: Settings
) -> None:
    app.state.container.planning_service._provider = FakeProvider()
    trip_id, csrf = await create_trip(client)

    started = await client.post(
        f"/api/v1/trips/{trip_id}/planning-runs",
        headers={"X-CSRF-Token": csrf},
        json={"profile": "PLAN_STANDARD", "instruction": "避免赶路"},
    )
    assert started.status_code == 200, started.text
    body = started.json()["data"]
    assert body["run"]["status"] == "succeeded"
    assert body["run"]["current_node"] == "approval_gate"
    proposal = body["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["estimated_cost_microusd"] == 980
    assert (await client.get(f"/api/v1/trips/{trip_id}/itinerary")).status_code == 404

    listed = await client.get(f"/api/v1/trips/{trip_id}/proposals")
    assert listed.json()["data"][0]["id"] == proposal["id"]
    applied = await client.post(
        f"/api/v1/proposals/{proposal['id']}/apply",
        headers={"X-CSRF-Token": csrf},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["status"] == "applied"
    itinerary = (await client.get(f"/api/v1/trips/{trip_id}/itinerary")).json()["data"]
    assert itinerary["version"] == 2
    assert itinerary["days"][0]["items"][0]["title"] == "游览拙政园"
    assert itinerary["estimated_total_cost_cents"] == 8000

    repeated = await client.post(
        f"/api/v1/proposals/{proposal['id']}/apply",
        headers={"X-CSRF-Token": csrf},
    )
    assert repeated.status_code == 409

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        run_count = await session.scalar(select(func.count()).select_from(PlanningRunRow))
        proposal_row = await session.scalar(select(ProposalRow))
        usage_count = await session.scalar(select(func.count()).select_from(ProviderUsageRow))
        version_count = await session.scalar(select(func.count()).select_from(ItineraryVersionRow))
    await database.dispose()
    assert run_count == 1
    assert proposal_row is not None
    assert "拙政园".encode() not in proposal_row.payload_ciphertext
    assert usage_count == 1
    assert version_count == 2


@pytest.mark.asyncio
async def test_planning_requires_confirmed_requirements(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    app.state.container.planning_service._provider = FakeProvider()
    trip_id, csrf = await create_trip(client, confirmed=False)
    response = await client.post(
        f"/api/v1/trips/{trip_id}/planning-runs",
        headers={"X-CSRF-Token": csrf},
        json={"profile": "PLAN_DEEP"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "planning_invalid_input"
