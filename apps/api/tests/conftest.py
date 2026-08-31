from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from travel_agent.api.app import create_app
from travel_agent.bootstrap.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        data_root=tmp_path / "data",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as test_client,
    ):
        yield test_client
