from __future__ import annotations

import os
from pathlib import Path

from travel_agent.bootstrap.settings import Settings
from travel_agent.modules.operations.application.health import HealthCheckResult
from travel_agent.shared.infrastructure.db.database import Database


class DatabaseReadinessCheck:
    name = "database"

    def __init__(self, database: Database) -> None:
        self._database = database

    async def run(self) -> HealthCheckResult:
        try:
            await self._database.ping()
        except Exception:
            return HealthCheckResult(self.name, "error", "database_unavailable")
        return HealthCheckResult(self.name, "ok")


class DirectoryReadinessCheck:
    name = "data_directories"

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root

    async def run(self) -> HealthCheckResult:
        required = ("db", "files", "exports", "cache", "tmp")
        unavailable = [
            name
            for name in required
            if not (path := self._data_root / name).is_dir() or not os.access(path, os.W_OK)
        ]
        if unavailable:
            return HealthCheckResult(self.name, "error", "runtime_directories_unavailable")
        return HealthCheckResult(self.name, "ok")


class MasterKeyReadinessCheck:
    name = "master_key"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self) -> HealthCheckResult:
        configured_key = self._settings.app_master_key
        key_bytes = (
            configured_key.get_secret_value().encode("utf-8") if configured_key is not None else b""
        )
        if len(key_bytes) >= 32:
            return HealthCheckResult(self.name, "ok")
        if self._settings.is_production:
            return HealthCheckResult(self.name, "error", "valid_master_key_required_in_production")
        return HealthCheckResult(
            self.name,
            "degraded",
            "valid_master_key_not_configured_for_development",
        )
