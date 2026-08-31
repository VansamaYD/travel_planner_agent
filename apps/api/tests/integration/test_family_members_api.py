import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.models import AuditEventRow, TravelerProfileRow
from travel_agent.shared.infrastructure.db.database import Database


async def initialize(client: httpx.AsyncClient) -> tuple[str, str, str]:
    response = await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "owner",
            "email": "owner@example.com",
            "display_name": "家庭所有者",
            "password": "correct horse battery staple",
            "family_name": "测试家庭",
        },
    )
    session = response.json()["data"]["session"]
    return session["families"][0]["id"], session["csrf_token"], session["user"]["id"]


def member_payload() -> dict[str, object]:
    return {
        "username": "traveler-one",
        "email": "traveler@example.com",
        "display_name": "旅行成员",
        "password": "member password is long enough",
        "role": "member",
        "profile": {
            "nickname": "小旅",
            "member_type": "senior",
            "birth_year": 1960,
            "discount_eligibilities": ["老年优惠"],
            "dietary_restrictions": ["少盐"],
            "allergies": ["花生"],
            "health_notes": "需要按时休息",
            "mobility_notes": "避免连续爬坡",
            "travel_preferences": ["慢节奏", "园林"],
            "sensitive_visibility": "private",
        },
    }


@pytest.mark.asyncio
async def test_owner_creates_member_and_private_profile_is_encrypted_and_redacted(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    family_id, csrf, _ = await initialize(client)
    created = await client.post(
        f"/api/v1/families/{family_id}/members",
        json=member_payload(),
        headers={"X-CSRF-Token": csrf},
    )

    assert created.status_code == 201
    membership_id = created.json()["data"]["id"]
    members = (await client.get(f"/api/v1/families/{family_id}/members")).json()["data"]
    member = next(item for item in members if item["membership_id"] == membership_id)
    assert member["profile"]["nickname"] == "小旅"
    assert member["profile"]["discount_eligibilities"] == ["老年优惠"]
    assert member["profile"]["allergies"] == []
    assert member["profile"]["health_notes"] == ""
    assert member["profile"]["sensitive_visibility"] == "private"

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        row = await session.get(TravelerProfileRow, membership_id)
    await database.dispose()
    assert row is not None
    assert "需要按时休息".encode() not in row.profile_ciphertext
    assert "花生".encode() not in row.profile_ciphertext

    duplicate = await client.post(
        f"/api/v1/families/{family_id}/members",
        json=member_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "resource_conflict"

    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"login": "traveler-one", "password": "member password is long enough"},
    )
    assert logged_in.status_code == 200
    own_members = (await client.get(f"/api/v1/families/{family_id}/members")).json()["data"]
    own_profile = next(item for item in own_members if item["membership_id"] == membership_id)[
        "profile"
    ]
    peer_identity = next(item for item in own_members if item["membership_id"] != membership_id)
    assert own_profile["allergies"] == ["花生"]
    assert own_profile["health_notes"] == "需要按时休息"
    assert peer_identity["username"] == ""
    assert peer_identity["email"] is None


@pytest.mark.asyncio
async def test_profile_optimistic_lock_role_change_removal_and_audit(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    family_id, csrf, owner_user_id = await initialize(client)
    created = await client.post(
        f"/api/v1/families/{family_id}/members",
        json={**member_payload(), "profile": {}},
        headers={"X-CSRF-Token": csrf},
    )
    membership_id = created.json()["data"]["id"]
    members = (await client.get(f"/api/v1/families/{family_id}/members")).json()["data"]
    owner = next(item for item in members if item["user_id"] == owner_user_id)

    profile = {
        "expected_version": 0,
        "nickname": "队长",
        "member_type": "adult",
        "birth_year": 1990,
        "discount_eligibilities": [],
        "dietary_restrictions": ["不吃香菜"],
        "allergies": [],
        "health_notes": "",
        "mobility_notes": "",
        "travel_preferences": ["摄影"],
        "sensitive_visibility": "private",
    }
    updated = await client.put(
        f"/api/v1/families/{family_id}/members/{owner['membership_id']}/profile",
        json=profile,
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version"] == 1

    stale = await client.put(
        f"/api/v1/families/{family_id}/members/{owner['membership_id']}/profile",
        json=profile,
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"

    changed = await client.patch(
        f"/api/v1/families/{family_id}/members/{membership_id}/role",
        json={"role": "guest"},
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 204
    removed = await client.delete(
        f"/api/v1/families/{family_id}/members/{membership_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert removed.status_code == 204
    remaining = (await client.get(f"/api/v1/families/{family_id}/members")).json()["data"]
    assert [item["user_id"] for item in remaining] == [owner_user_id]

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.event_type.in_(
                    (
                        "family.member_created",
                        "traveler_profile.updated",
                        "family.member_role_changed",
                        "family.member_removed",
                    )
                )
            )
        )
    await database.dispose()
    assert event_count == 4
