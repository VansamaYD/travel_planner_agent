from pathlib import Path

import pytest
from sqlalchemy import text

from travel_agent.bootstrap.settings import Settings
from travel_agent.shared.infrastructure.db.database import Database
from travel_agent.shared.infrastructure.db.uow import SqlAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_uow_rolls_back_without_explicit_commit(tmp_path: Path) -> None:
    database = Database.from_settings(
        Settings(
            _env_file=None,
            app_env="test",
            data_root=tmp_path,
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'uow.db'}",
        )
    )
    async with database.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))

    async with SqlAlchemyUnitOfWork(database.session_factory) as uow:
        await uow.session.execute(text("INSERT INTO sample (id) VALUES (1)"))

    async with database.engine.connect() as connection:
        count = await connection.scalar(text("SELECT COUNT(*) FROM sample"))
    await database.dispose()

    assert count == 0


@pytest.mark.asyncio
async def test_uow_persists_explicit_commit(tmp_path: Path) -> None:
    database = Database.from_settings(
        Settings(
            _env_file=None,
            app_env="test",
            data_root=tmp_path,
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'uow.db'}",
        )
    )
    async with database.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))

    async with SqlAlchemyUnitOfWork(database.session_factory) as uow:
        await uow.session.execute(text("INSERT INTO sample (id) VALUES (1)"))
        await uow.commit()

    async with database.engine.connect() as connection:
        count = await connection.scalar(text("SELECT COUNT(*) FROM sample"))
    await database.dispose()

    assert count == 1
