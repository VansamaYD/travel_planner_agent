from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

from sqlalchemy import Select, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.access.application.ports import CredentialRecord
from travel_agent.modules.access.domain.models import (
    AuthenticatedSession,
    FamilyRole,
    FamilySummary,
    SystemRole,
    UserIdentity,
    UserStatus,
)
from travel_agent.modules.access.infrastructure.models import (
    AuditEventRow,
    FamilyMembershipRow,
    FamilyRow,
    SessionRow,
    SystemStateRow,
    UserRow,
)
from travel_agent.modules.access.infrastructure.security import AesGcmTextProtector
from travel_agent.shared.domain.ids import new_uuid7


class SqlAlchemyAccessStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        protector: AesGcmTextProtector,
    ) -> None:
        self._session_factory = session_factory
        self._protector = protector
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Access store is not active")
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        await self.session.commit()

    async def is_initialized(self) -> bool:
        state = await self.session.get(SystemStateRow, 1)
        return state is not None and state.initialized_at is not None

    async def claim_initialization(self, initialized_at: datetime, recovery_hash: str) -> bool:
        result = await self.session.execute(
            update(SystemStateRow)
            .where(SystemStateRow.id == 1, SystemStateRow.initialized_at.is_(None))
            .values(initialized_at=initialized_at, recovery_code_hash=recovery_hash)
            .returning(SystemStateRow.id)
        )
        return result.scalar_one_or_none() == 1

    async def add_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        system_role: SystemRole,
        created_at: datetime,
    ) -> UserIdentity:
        row = UserRow(
            id=user_id,
            username_normalized=username,
            email_normalized=email,
            display_name_ciphertext=self._protector.encrypt(
                display_name, context="user.display_name"
            ),
            password_hash=password_hash,
            system_role=system_role.value,
            status=UserStatus.ACTIVE.value,
            session_epoch=0,
            locale="zh-CN",
            timezone="Asia/Shanghai",
            created_at=created_at,
        )
        self.session.add(row)
        await self.session.flush()
        return self._identity(row)

    async def add_family(
        self, *, family_id: str, name: str, owner_user_id: str, created_at: datetime
    ) -> None:
        self.session.add(
            FamilyRow(
                id=family_id,
                name_ciphertext=self._protector.encrypt(name, context="family.name"),
                owner_user_id=owner_user_id,
                default_locale="zh-CN",
                settings_json={},
                storage_limit_bytes=20 * 1024**3,
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def add_membership(
        self,
        *,
        membership_id: str,
        family_id: str,
        user_id: str,
        role: FamilyRole,
        joined_at: datetime,
    ) -> None:
        self.session.add(
            FamilyMembershipRow(
                id=membership_id,
                family_id=family_id,
                user_id=user_id,
                role=role.value,
                status="active",
                joined_at=joined_at,
            )
        )

    async def find_user_by_login(self, normalized_login: str) -> CredentialRecord | None:
        statement = select(UserRow).where(
            or_(
                UserRow.username_normalized == normalized_login,
                UserRow.email_normalized == normalized_login,
            )
        )
        row = (await self.session.scalars(statement)).one_or_none()
        if row is None:
            return None
        return CredentialRecord(self._identity(row), row.password_hash)

    async def mark_login(self, user_id: str, logged_in_at: datetime) -> None:
        await self.session.execute(
            update(UserRow).where(UserRow.id == user_id).values(last_login_at=logged_in_at)
        )

    async def add_session(
        self,
        *,
        session_id: str,
        token_hash: str,
        csrf_token: str,
        user_id: str,
        session_epoch: int,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.session.add(
            SessionRow(
                id=session_id,
                token_hash=token_hash,
                csrf_ciphertext=self._protector.encrypt(csrf_token, context="session.csrf"),
                user_id=user_id,
                session_epoch=session_epoch,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    async def get_session(self, token_hash: str, now: datetime) -> AuthenticatedSession | None:
        statement = (
            select(SessionRow, UserRow)
            .join(UserRow, UserRow.id == SessionRow.user_id)
            .where(
                SessionRow.token_hash == token_hash,
                SessionRow.revoked_at.is_(None),
            )
        )
        record = (await self.session.execute(statement)).one_or_none()
        if record is None:
            return None
        session_row, user_row = record
        expires_at = _aware(session_row.expires_at)
        if expires_at <= now or session_row.session_epoch != user_row.session_epoch:
            return None
        if user_row.status != UserStatus.ACTIVE.value:
            return None
        families = await self.list_families(user_row.id)
        return AuthenticatedSession(
            id=session_row.id,
            user=self._identity(user_row),
            csrf_token=self._protector.decrypt(session_row.csrf_ciphertext, context="session.csrf"),
            expires_at=expires_at,
            families=families,
        )

    async def revoke_session(self, session_id: str, revoked_at: datetime) -> None:
        await self.session.execute(
            update(SessionRow).where(SessionRow.id == session_id).values(revoked_at=revoked_at)
        )

    async def list_families(self, user_id: str) -> tuple[FamilySummary, ...]:
        statement: Select[tuple[FamilyMembershipRow, FamilyRow]] = (
            select(FamilyMembershipRow, FamilyRow)
            .join(FamilyRow, FamilyRow.id == FamilyMembershipRow.family_id)
            .where(
                FamilyMembershipRow.user_id == user_id,
                FamilyMembershipRow.status == "active",
            )
            .order_by(FamilyMembershipRow.joined_at)
        )
        records = (await self.session.execute(statement)).all()
        return tuple(
            FamilySummary(
                id=family.id,
                name=self._protector.decrypt(family.name_ciphertext, context="family.name"),
                role=FamilyRole(membership.role),
            )
            for membership, family in records
        )

    async def update_family_name(self, family_id: str, name: str) -> bool:
        result = await self.session.execute(
            update(FamilyRow)
            .where(FamilyRow.id == family_id)
            .values(name_ciphertext=self._protector.encrypt(name, context="family.name"))
            .returning(FamilyRow.id)
        )
        return result.scalar_one_or_none() is not None

    async def add_audit(
        self,
        *,
        event_type: str,
        actor_user_id: str | None,
        subject_type: str,
        subject_id: str | None,
        request_id: str | None,
        details: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            AuditEventRow(
                id=new_uuid7(),
                event_type=event_type,
                actor_user_id=actor_user_id,
                source_type="user" if actor_user_id else "anonymous",
                subject_type=subject_type,
                subject_id=subject_id,
                request_id=request_id,
                details_json=details,
                created_at=created_at,
            )
        )

    def _identity(self, row: UserRow) -> UserIdentity:
        return UserIdentity(
            id=row.id,
            username=row.username_normalized,
            email=row.email_normalized,
            display_name=self._protector.decrypt(
                row.display_name_ciphertext, context="user.display_name"
            ),
            system_role=SystemRole(row.system_role),
            status=UserStatus(row.status),
            session_epoch=row.session_epoch,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
