import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.models import AuditEventRow
from travel_agent.modules.trips.infrastructure.models import OutboxEventRow, TripVersionRow
from travel_agent.shared.infrastructure.db.database import Database


async def initialize(client: httpx.AsyncClient) -> tuple[str, str, str]:
    response = await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "owner",
            "email": "owner@example.com",
            "display_name": "旅行发起人",
            "password": "correct horse battery staple",
            "family_name": "周末旅行组",
        },
    )
    session = response.json()["data"]["session"]
    family_id = session["families"][0]["id"]
    members = await client.get(f"/api/v1/families/{family_id}/members")
    membership_id = members.json()["data"][0]["membership_id"]
    return family_id, membership_id, session["csrf_token"]


def trip_payload(family_id: str, membership_id: str) -> dict[str, object]:
    return {
        "family_id": family_id,
        "title": "杭州三日慢旅行",
        "visibility": "family",
        "membership_ids": [membership_id],
        "requirements": {
            "input_mode": "form",
            "origin": "上海",
            "destinations": ["杭州", "西湖"],
            "start_date": "2026-10-02",
            "end_date": "2026-10-04",
            "budget_cents": 360000,
            "currency": "CNY",
            "styles": ["美食", "休闲"],
            "pace": "leisure",
            "transportation": ["高铁", "地铁公交线路", "步行"],
            "hard_constraints": ["避免凌晨出发"],
            "soft_preferences": ["优先本地餐厅"],
            "assumptions": ["从上海虹桥出发"],
            "source_text": "",
            "confirmed": False,
        },
    }


@pytest.mark.asyncio
async def test_trip_draft_is_versioned_encrypted_and_audited(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    family_id, membership_id, csrf = await initialize(client)
    created = await client.post(
        "/api/v1/trips",
        json=trip_payload(family_id, membership_id),
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201, created.text
    trip = created.json()["data"]
    assert trip["version"] == 1
    assert trip["participants"][0]["display_name"] == "旅行发起人"
    assert trip["warnings"]

    listed = await client.get(f"/api/v1/trips?family_id={family_id}")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["destinations"] == ["杭州", "西湖"]

    update_payload = trip_payload(family_id, membership_id)
    update_payload.pop("family_id")
    update_payload["expected_version"] = 1
    update_payload["title"] = "杭州三日家庭旅行"
    requirements = update_payload["requirements"]
    assert isinstance(requirements, dict)
    requirements["confirmed"] = True
    updated = await client.patch(
        f"/api/v1/trips/{trip['id']}",
        json=update_payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["version"] == 2
    assert updated.json()["data"]["requirements"]["confirmed"] is True

    stale = await client.patch(
        f"/api/v1/trips/{trip['id']}",
        json=update_payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "trip_version_conflict"

    versions = await client.get(f"/api/v1/trips/{trip['id']}/versions")
    assert [item["version_no"] for item in versions.json()["data"]] == [2, 1]
    original = await client.get(f"/api/v1/trips/{trip['id']}/versions/1")
    assert original.json()["data"]["snapshot"]["title"] == "杭州三日慢旅行"

    deleted = await client.delete(f"/api/v1/trips/{trip['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).status_code == 404
    recycle_bin = await client.get(f"/api/v1/trips/deleted?family_id={family_id}")
    assert [item["id"] for item in recycle_bin.json()["data"]] == [trip["id"]]
    restored = await client.post(
        f"/api/v1/trips/{trip['id']}/restore", headers={"X-CSRF-Token": csrf}
    )
    assert restored.status_code == 200
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).status_code == 200

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        rows = tuple(await session.scalars(select(TripVersionRow)))
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.event_type.in_(
                    ("trip.created", "trip.updated", "trip.deleted", "trip.restored")
                )
            )
        )
        outbox_count = await session.scalar(select(func.count()).select_from(OutboxEventRow))
    await database.dispose()
    assert len(rows) == 2
    assert all("杭州".encode() not in row.snapshot_ciphertext for row in rows)
    assert audit_count == 4
    assert outbox_count == 4


@pytest.mark.asyncio
async def test_trip_validation_and_csrf_are_enforced(client: httpx.AsyncClient) -> None:
    family_id, membership_id, csrf = await initialize(client)
    payload = trip_payload(family_id, membership_id)
    requirements = payload["requirements"]
    assert isinstance(requirements, dict)
    requirements["end_date"] = "2026-09-01"

    invalid = await client.post("/api/v1/trips", json=payload, headers={"X-CSRF-Token": csrf})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "trip_invalid_input"

    requirements["end_date"] = "2026-10-04"
    missing_csrf = await client.post("/api/v1/trips", json=payload)
    assert missing_csrf.status_code == 403
