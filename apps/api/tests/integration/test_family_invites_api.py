import re

import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.models import AuditEventRow, FamilyInviteRow
from travel_agent.shared.infrastructure.db.database import Database


async def initialize(client: httpx.AsyncClient) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "owner",
            "email": "owner@example.com",
            "display_name": "家庭所有者",
            "password": "correct horse battery staple",
            "family_name": "目标家庭",
        },
    )
    session = response.json()["data"]["session"]
    return session["families"][0]["id"], session["csrf_token"]


async def create_invite(
    client: httpx.AsyncClient,
    family_id: str,
    csrf: str,
    role: str = "member",
) -> httpx.Response:
    return await client.post(
        f"/api/v1/families/{family_id}/invites",
        json={"role": role, "expires_in_days": 7},
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.asyncio
async def test_invite_registration_is_single_use_hashed_and_audited(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    family_id, csrf = await initialize(client)
    issued = await create_invite(client, family_id, csrf)

    assert issued.status_code == 201
    code = issued.json()["data"]["code"]
    invite_id = issued.json()["data"]["invite"]["id"]
    assert re.fullmatch(r"(?:[A-Z2-7]{4}-){5}[A-Z2-7]{4}", code)

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        row = await session.get(FamilyInviteRow, invite_id)
    await database.dispose()
    assert row is not None
    assert code not in row.token_hash
    assert len(row.token_hash) == 64

    malformed = await client.post(
        "/api/v1/family-invites/register",
        json={
            "code": "旅行旅行旅行旅行旅行旅行旅行旅行旅行旅行",
            "username": "invalid-code-user",
            "email": None,
            "display_name": "无效邀请码",
            "password": "invalid code password",
        },
    )
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "invalid_invite"

    registered = await client.post(
        "/api/v1/family-invites/register",
        json={
            "code": code,
            "username": "invited-user",
            "email": "invited@example.com",
            "display_name": "受邀成员",
            "password": "invited account password",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["data"]["username"] == "invited-user"

    reused = await client.post(
        "/api/v1/family-invites/register",
        json={
            "code": code,
            "username": "second-user",
            "email": None,
            "display_name": "第二个人",
            "password": "another invited password",
        },
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_invite"

    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"login": "invited-user", "password": "invited account password"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["families"][0]["id"] == family_id

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.event_type.in_(("family.invite_created", "family.invite_registered"))
            )
        )
    await database.dispose()
    assert event_count == 2


@pytest.mark.asyncio
async def test_existing_account_accepts_invite_and_revoked_invite_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    target_family_id, owner_csrf = await initialize(client)
    second_family = await client.post(
        "/api/v1/families",
        json={"name": "成员原家庭"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    second_family_id = second_family.json()["data"]["id"]
    await client.post(
        f"/api/v1/families/{second_family_id}/members",
        json={
            "username": "existing-user",
            "email": None,
            "display_name": "已有用户",
            "password": "existing user password",
            "role": "member",
            "profile": {},
        },
        headers={"X-CSRF-Token": owner_csrf},
    )
    issued = await create_invite(client, target_family_id, owner_csrf)
    code = issued.json()["data"]["code"]

    revoked_issue = await create_invite(client, target_family_id, owner_csrf, role="guest")
    revoked_id = revoked_issue.json()["data"]["invite"]["id"]
    revoked_code = revoked_issue.json()["data"]["code"]
    revoked = await client.delete(
        f"/api/v1/families/{target_family_id}/invites/{revoked_id}",
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert revoked.status_code == 204

    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": owner_csrf})
    login = await client.post(
        "/api/v1/auth/login",
        json={"login": "existing-user", "password": "existing user password"},
    )
    member_csrf = login.json()["data"]["csrf_token"]

    rejected = await client.post(
        "/api/v1/family-invites/accept",
        json={"code": revoked_code},
        headers={"X-CSRF-Token": member_csrf},
    )
    assert rejected.status_code == 400
    accepted = await client.post(
        "/api/v1/family-invites/accept",
        json={"code": code},
        headers={"X-CSRF-Token": member_csrf},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["family_id"] == target_family_id

    current = await client.get("/api/v1/auth/session")
    assert {family["id"] for family in current.json()["data"]["families"]} == {
        second_family_id,
        target_family_id,
    }
    duplicate = await client.post(
        "/api/v1/family-invites/accept",
        json={"code": code},
        headers={"X-CSRF-Token": member_csrf},
    )
    assert duplicate.status_code == 400
