from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import cast

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from travel_agent.bootstrap.settings import Settings


@dataclass(slots=True)
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @classmethod
    def from_settings(cls, settings: Settings) -> Database:
        url = settings.effective_database_url
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"timeout": 5} if url.startswith("sqlite") else {},
        )
        if url.startswith("sqlite"):
            cls._configure_sqlite(engine)
        return cls(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
        )

    @staticmethod
    def _configure_sqlite(engine: AsyncEngine) -> None:
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
            connection = cast(sqlite3.Connection, dbapi_connection)
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
