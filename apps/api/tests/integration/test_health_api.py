import httpx
import pytest


@pytest.mark.asyncio
async def test_liveness_returns_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-Id": "test-request"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request"
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_checks_database_directories_and_key(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {check["name"] for check in body["checks"]} == {
        "database",
        "data_directories",
        "master_key",
    }
