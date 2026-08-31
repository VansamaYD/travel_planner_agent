from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.access.domain.models import (
    FamilyInvite,
    FamilyRole,
    SystemRole,
    UserStatus,
)
from travel_agent.modules.access.infrastructure.models import (
    AuditEventRow,
    FamilyInviteRow,
    FamilyMembershipRow,
    UserRow,
)
from travel_agent.modules.access.infrastructure.security import AesGcmTextProtector
from travel_agent.shared.domain.ids import new_uuid7


class SqlAlchemyInviteStore:
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
            raise RuntimeError("Invite store is not active")
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

    async def actor_role(self, family_id: str, user_id: str) -> FamilyRole | None:
        role = await self.session.scalar(
            select(FamilyMembershipRow.role).where(
                FamilyMembershipRow.family_id == family_id,
                FamilyMembershipRow.user_id == user_id,
                FamilyMembershipRow.status == "active",
            )
        )
        return FamilyRole(role) if role else None

    async def add_invite(
        self,
        *,
        invite_id: str,
        family_id: str,
        token_hash: str,
        role: FamilyRole,
        created_by_user_id: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.session.add(
            FamilyInviteRow(
                id=invite_id,
                family_id=family_id,
                token_hash=token_hash,
                role=role.value,
                status="active",
                created_by_user_id=created_by_user_id,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    async def list_invites(self, family_id: str, now: datetime) -> tuple[FamilyInvite, ...]:
        rows = (
            await self.session.scalars(
                select(FamilyInviteRow)
                .where(FamilyInviteRow.family_id == family_id)
                .order_by(FamilyInviteRow.created_at.desc())
                .limit(50)
            )
        ).all()
        return tuple(self._invite(row, now) for row in rows)

    async def revoke_invite(self, family_id: str, invite_id: str, now: datetime) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(FamilyInviteRow)
                .where(
                    FamilyInviteRow.id == invite_id,
                    FamilyInviteRow.family_id == family_id,
                    FamilyInviteRow.status == "active",
                    FamilyInviteRow.expires_at > now,
                )
                .values(status="revoked", revoked_at=now)
            ),
        )
        return result.rowcount == 1

    async def find_invite(self, token_hash: str, now: datetime) -> FamilyInvite | None:
        row = await self.session.scalar(
            select(FamilyInviteRow).where(
                FamilyInviteRow.token_hash == token_hash,
                FamilyInviteRow.status == "active",
                FamilyInviteRow.expires_at > now,
            )
        )
        return self._invite(row, now) if row else None

    async def has_active_membership(self, family_id: str, user_id: str) -> bool:
        membership_id = await self.session.scalar(
            select(FamilyMembershipRow.id).where(
                FamilyMembershipRow.family_id == family_id,
                FamilyMembershipRow.user_id == user_id,
                FamilyMembershipRow.status == "active",
            )
        )
        return membership_id is not None

    async def login_exists(self, username: str, email: str | None) -> bool:
        conditions = [UserRow.username_normalized == username]
        if email:
            conditions.append(UserRow.email_normalized == email)
        return (
            await self.session.scalar(select(UserRow.id).where(or_(*conditions)).limit(1))
            is not None
        )

    async def claim_invite(self, invite_id: str, user_id: str, accepted_at: datetime) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(FamilyInviteRow)
                .where(
                    FamilyInviteRow.id == invite_id,
                    FamilyInviteRow.status == "active",
                    FamilyInviteRow.expires_at > accepted_at,
                )
                .values(
                    status="accepted",
                    accepted_by_user_id=user_id,
                    accepted_at=accepted_at,
                )
            ),
        )
        return result.rowcount == 1

    async def activate_membership(
        self,
        *,
        membership_id: str,
        family_id: str,
        user_id: str,
        role: FamilyRole,
        joined_at: datetime,
    ) -> None:
        existing = await self.session.scalar(
            select(FamilyMembershipRow).where(
                FamilyMembershipRow.family_id == family_id,
                FamilyMembershipRow.user_id == user_id,
            )
        )
        if existing is None:
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
            return
        existing.role = role.value
        existing.status = "active"
        existing.joined_at = joined_at

    async def add_invited_user(
        self,
        *,
        user_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        created_at: datetime,
    ) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                sqlite_insert(UserRow)
                .values(
                    id=user_id,
                    username_normalized=username,
                    email_normalized=email,
                    display_name_ciphertext=self._protector.encrypt(
                        display_name, context="user.display_name"
                    ),
                    password_hash=password_hash,
                    system_role=SystemRole.MEMBER.value,
                    status=UserStatus.ACTIVE.value,
                    session_epoch=0,
                    locale="zh-CN",
                    timezone="Asia/Shanghai",
                    created_at=created_at,
                )
                .on_conflict_do_nothing()
            ),
        )
        return result.rowcount == 1

    async def add_audit(
        self,
        *,
        event_type: str,
        actor_user_id: str,
        subject_type: str,
        subject_id: str,
        request_id: str | None,
        details: dict[str, Any],
        created_at: datetime,
    ) -> None:
        self.session.add(
            AuditEventRow(
                id=new_uuid7(),
                event_type=event_type,
                actor_user_id=actor_user_id,
                source_type="user",
                subject_type=subject_type,
                subject_id=subject_id,
                request_id=request_id,
                details_json=details,
                created_at=created_at,
            )
        )

    @staticmethod
    def _invite(row: FamilyInviteRow, now: datetime) -> FamilyInvite:
        expires_at = _aware(row.expires_at)
        status = "expired" if row.status == "active" and expires_at <= now else row.status
        return FamilyInvite(
            id=row.id,
            family_id=row.family_id,
            role=FamilyRole(row.role),
            status=status,
            created_by_user_id=row.created_by_user_id,
            created_at=_aware(row.created_at),
            expires_at=expires_at,
            accepted_by_user_id=row.accepted_by_user_id,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
