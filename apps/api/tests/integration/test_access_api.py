import re

import httpx
import pytest
from sqlalchemy import func, select

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.models import (
    AuditEventRow,
    FamilyRow,
    SystemStateRow,
    UserRow,
)
from travel_agent.shared.infrastructure.db.database import Database


async def initialize(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post(
        "/api/v1/setup/initialize",
        json={
            "username": "旅行管理员",
            "email": "admin@example.com",
            "display_name": "家庭管理员",
            "password": "correct horse battery staple",
            "family_name": "我们的旅行家庭",
        },
    )


@pytest.mark.asyncio
async def test_initialization_creates_admin_family_session_and_one_time_recovery_code(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    before = await client.get("/api/v1/setup/status")
    response = await initialize(client)
    after = await client.get("/api/v1/setup/status")

    assert before.json()["data"] == {"initialized": False}
    assert response.status_code == 201
    assert after.json()["data"] == {"initialized": True}
    assert "travel_session=" in response.headers["set-cookie"]
    data = response.json()["data"]
    assert re.fullmatch(r"(?:[A-Z2-7]{4}-){7}[A-Z2-7]{4}", data["recovery_code"])
    assert data["session"]["user"]["system_role"] == "admin"
    assert data["session"]["families"][0]["role"] == "owner"

    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        user_row = (await session.scalars(select(UserRow))).one()
        family_row = (await session.scalars(select(FamilyRow))).one()
        system_state = (await session.scalars(select(SystemStateRow))).one()
    await database.dispose()
    assert "家庭管理员".encode() not in user_row.display_name_ciphertext
    assert "我们的旅行家庭".encode() not in family_row.name_ciphertext
    assert system_state.recovery_code_hash is not None
    assert data["recovery_code"] not in system_state.recovery_code_hash

    repeated = await initialize(client)
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "already_initialized"


@pytest.mark.asyncio
async def test_login_session_csrf_family_creation_and_logout(client: httpx.AsyncClient) -> None:
    initialized = await initialize(client)
    csrf = initialized.json()["data"]["session"]["csrf_token"]

    current = await client.get("/api/v1/auth/session")
    assert current.status_code == 200
    assert current.json()["data"]["user"]["username"] == "旅行管理员"

    rejected = await client.post("/api/v1/families", json={"name": "第二个家庭"})
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_mismatch"

    created = await client.post(
        "/api/v1/families",
        json={"name": "第二个家庭"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201
    families = await client.get("/api/v1/families")
    assert [family["name"] for family in families.json()["data"]] == [
        "我们的旅行家庭",
        "第二个家庭",
    ]

    logged_out = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logged_out.status_code == 204
    assert (await client.get("/api/v1/auth/session")).status_code == 401

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"login": "admin@example.com", "password": "correct horse battery staple"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["families"][1]["name"] == "第二个家庭"


@pytest.mark.asyncio
async def test_failed_login_is_generic_and_audited(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    await initialize(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"login": "admin@example.com", "password": "incorrect password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    database = Database.from_settings(settings)
    async with database.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.event_type == "auth.login_failed")
        )
    await database.dispose()
    assert count == 1
