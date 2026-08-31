from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from travel_agent.bootstrap.settings import Settings, get_settings
from travel_agent.modules.access.application.invite_service import FamilyInviteService
from travel_agent.modules.access.application.member_service import FamilyMemberService
from travel_agent.modules.access.application.service import AccessService
from travel_agent.modules.access.infrastructure.invite_store import SqlAlchemyInviteStore
from travel_agent.modules.access.infrastructure.member_store import SqlAlchemyMemberStore
from travel_agent.modules.access.infrastructure.rate_limit import LoginRateLimiter
from travel_agent.modules.access.infrastructure.security import (
    AesGcmTextProtector,
    Argon2idHasher,
    SecureTokenIssuer,
    SystemClock,
    resolve_protection_key,
)
from travel_agent.modules.access.infrastructure.store import SqlAlchemyAccessStore
from travel_agent.modules.itinerary.application.ports import ItineraryStore
from travel_agent.modules.itinerary.application.service import ItineraryService
from travel_agent.modules.itinerary.infrastructure.store import SqlAlchemyItineraryStore
from travel_agent.modules.operations.application.health import HealthService
from travel_agent.modules.operations.infrastructure.health_checks import (
    DatabaseReadinessCheck,
    DirectoryReadinessCheck,
    MasterKeyReadinessCheck,
)
from travel_agent.modules.trips.application.ports import TripStore
from travel_agent.modules.trips.application.service import TripService
from travel_agent.modules.trips.infrastructure.store import SqlAlchemyTripStore
from travel_agent.shared.infrastructure.db.database import Database


@dataclass(slots=True)
class Container:
    settings: Settings
    database: Database
    health_service: HealthService
    access_service: AccessService
    family_member_service: FamilyMemberService
    family_invite_service: FamilyInviteService
    trip_service: TripService
    itinerary_service: ItineraryService
    login_rate_limiter: LoginRateLimiter
    invite_registration_rate_limiter: LoginRateLimiter

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

    def member_store_factory() -> SqlAlchemyMemberStore:
        return SqlAlchemyMemberStore(database.session_factory, protector)

    def invite_store_factory() -> SqlAlchemyInviteStore:
        return SqlAlchemyInviteStore(database.session_factory, protector)

    def trip_store_factory() -> TripStore:
        return SqlAlchemyTripStore(database.session_factory, protector)

    def itinerary_store_factory() -> ItineraryStore:
        return SqlAlchemyItineraryStore(database.session_factory, protector)

    password_hasher = Argon2idHasher()
    token_issuer = SecureTokenIssuer()
    access_service = AccessService(
        store_factory=store_factory,
        password_hasher=password_hasher,
        token_issuer=token_issuer,
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
        family_member_service=FamilyMemberService(
            store_factory=member_store_factory,
            password_hasher=password_hasher,
            clock=SystemClock(),
        ),
        family_invite_service=FamilyInviteService(
            store_factory=invite_store_factory,
            token_issuer=token_issuer,
            password_hasher=password_hasher,
            clock=SystemClock(),
        ),
        trip_service=TripService(store_factory=trip_store_factory, clock=SystemClock()),
        itinerary_service=ItineraryService(
            store_factory=itinerary_store_factory, clock=SystemClock()
        ),
        login_rate_limiter=LoginRateLimiter(),
        invite_registration_rate_limiter=LoginRateLimiter(attempts=3, window_seconds=600),
    )
