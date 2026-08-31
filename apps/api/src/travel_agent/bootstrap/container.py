from __future__ import annotations

from dataclasses import dataclass

from travel_agent.bootstrap.settings import Settings, get_settings
from travel_agent.modules.operations.application.health import HealthService
from travel_agent.modules.operations.infrastructure.health_checks import (
    DatabaseReadinessCheck,
    DirectoryReadinessCheck,
    MasterKeyReadinessCheck,
)
from travel_agent.shared.infrastructure.db.database import Database


@dataclass(slots=True)
class Container:
    settings: Settings
    database: Database
    health_service: HealthService

    async def startup(self) -> None:
        self.settings.ensure_runtime_directories()
        await self.database.ping()

    async def shutdown(self) -> None:
        await self.database.dispose()


def build_container(settings: Settings | None = None) -> Container:
    resolved_settings = settings or get_settings()
    database = Database.from_settings(resolved_settings)
    health_service = HealthService(
        checks=(
            DatabaseReadinessCheck(database),
            DirectoryReadinessCheck(resolved_settings.data_root),
            MasterKeyReadinessCheck(resolved_settings),
        )
    )
    return Container(
        settings=resolved_settings,
        database=database,
        health_service=health_service,
    )
