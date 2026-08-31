from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from travel_agent.bootstrap.settings import Settings, get_settings
from travel_agent.modules.access.application.service import AccessService
from travel_agent.modules.access.infrastructure.rate_limit import LoginRateLimiter
from travel_agent.modules.access.infrastructure.security import (
    AesGcmTextProtector,
    Argon2idHasher,
    SecureTokenIssuer,
    SystemClock,
    resolve_protection_key,
)
from travel_agent.modules.access.infrastructure.store import SqlAlchemyAccessStore
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
    access_service: AccessService
    login_rate_limiter: LoginRateLimiter

    async def startup(self) -> None:
        self.settings.ensure_runtime_directories()
        await self.database.ping()

    async def shutdown(self) -> None:
        await self.database.dispose()


def build_container(settings: Settings | None = None) -> Container:
    resolved_settings = settings or get_settings()
    database = Database.from_settings(resolved_settings)
    protector = AesGcmTextProtector(resolve_protection_key(resolved_settings))

    def store_factory() -> SqlAlchemyAccessStore:
        return SqlAlchemyAccessStore(database.session_factory, protector)

    access_service = AccessService(
        store_factory=store_factory,
        password_hasher=Argon2idHasher(),
        token_issuer=SecureTokenIssuer(),
        clock=SystemClock(),
        session_lifetime=timedelta(days=resolved_settings.session_lifetime_days),
    )
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
        access_service=access_service,
        login_rate_limiter=LoginRateLimiter(),
    )
