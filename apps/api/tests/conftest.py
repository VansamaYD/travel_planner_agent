from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from travel_agent.api.app import create_app
from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.access.infrastructure.models import SystemStateRow
from travel_agent.shared.infrastructure.db.base import Base


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        data_root=tmp_path / "data",
        config_root=tmp_path / "config",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    container = app.state.container
    async with container.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with container.database.session_factory() as session:
        session.add(SystemStateRow(id=1))
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as test_client,
    ):
        yield test_client
