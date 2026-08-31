import httpx
import pytest

from travel_agent.bootstrap.settings import Settings


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
async def test_runtime_integration_settings_are_encrypted_and_secrets_are_masked(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    csrf = await initialize(client)
    response = await client.patch(
        "/api/v1/settings/integrations",
        headers={"X-CSRF-Token": csrf},
        json={
            "values": {
                "deepseek_api_key": "secret-deepseek-key",
                "deepseek_model": "deepseek-chat",
                "xhs_research_enabled": True,
            }
        },
    )

    assert response.status_code == 202
    assert response.json()["meta"]["restart_required"] is True
    fields = {value["key"]: value for value in response.json()["data"]}
    assert fields["deepseek_api_key"]["configured"] is True
    assert fields["deepseek_api_key"]["value"] == ""
    encrypted = (settings.config_root / "runtime-integrations.enc").read_bytes()
    assert b"secret-deepseek-key" not in encrypted

    listed = await client.get("/api/v1/settings/integrations")
    assert listed.status_code == 200
    assert "secret-deepseek-key" not in listed.text
