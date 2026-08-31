from __future__ import annotations

import json
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.access.domain.models import (
    FamilyMember,
    FamilyRole,
    MemberType,
    SensitiveVisibility,
    SystemRole,
    TravelerProfile,
    UserIdentity,
    UserStatus,
)
from travel_agent.modules.access.infrastructure.models import (
    AuditEventRow,
    FamilyMembershipRow,
    TravelerProfileRow,
    UserRow,
)
from travel_agent.modules.access.infrastructure.security import AesGcmTextProtector
from travel_agent.shared.domain.ids import new_uuid7


class SqlAlchemyMemberStore:
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
            raise RuntimeError("Member store is not active")
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
        statement = select(FamilyMembershipRow.role).where(
            FamilyMembershipRow.family_id == family_id,
            FamilyMembershipRow.user_id == user_id,
            FamilyMembershipRow.status == "active",
        )
        role = (await self.session.scalars(statement)).one_or_none()
        return FamilyRole(role) if role else None

    async def list_members(self, family_id: str) -> tuple[FamilyMember, ...]:
        statement = (
            select(FamilyMembershipRow, UserRow, TravelerProfileRow)
            .join(UserRow, UserRow.id == FamilyMembershipRow.user_id)
            .outerjoin(
                TravelerProfileRow,
                TravelerProfileRow.membership_id == FamilyMembershipRow.id,
            )
            .where(
                FamilyMembershipRow.family_id == family_id,
                FamilyMembershipRow.status == "active",
            )
            .order_by(FamilyMembershipRow.joined_at)
        )
        return tuple(self._member(*record) for record in (await self.session.execute(statement)))

    async def get_member(self, family_id: str, membership_id: str) -> FamilyMember | None:
        statement = (
            select(FamilyMembershipRow, UserRow, TravelerProfileRow)
            .join(UserRow, UserRow.id == FamilyMembershipRow.user_id)
            .outerjoin(
                TravelerProfileRow,
                TravelerProfileRow.membership_id == FamilyMembershipRow.id,
            )
            .where(
                FamilyMembershipRow.family_id == family_id,
                FamilyMembershipRow.id == membership_id,
                FamilyMembershipRow.status == "active",
            )
        )
        record = (await self.session.execute(statement)).one_or_none()
        return self._member(*record) if record else None

    async def login_exists(self, username: str, email: str | None) -> bool:
        conditions = [UserRow.username_normalized == username]
        if email:
            conditions.append(UserRow.email_normalized == email)
        return (
            await self.session.scalar(select(UserRow.id).where(or_(*conditions)).limit(1))
            is not None
        )

    async def create_member(
        self,
        *,
        family_id: str,
        user_id: str,
        membership_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password_hash: str,
        role: FamilyRole,
        profile: TravelerProfile,
        actor_user_id: str,
        created_at: datetime,
    ) -> bool:
        user_insert = cast(
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
        if user_insert.rowcount != 1:
            return False
        self.session.add(
            FamilyMembershipRow(
                id=membership_id,
                family_id=family_id,
                user_id=user_id,
                role=role.value,
                status="active",
                joined_at=created_at,
            )
        )
        await self.session.flush()
        self.session.add(
            TravelerProfileRow(
                membership_id=membership_id,
                profile_ciphertext=self._encrypt_profile(profile),
                version=profile.version,
                updated_by_user_id=actor_user_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        return True

    async def save_profile(
        self,
        *,
        membership_id: str,
        expected_version: int,
        profile: TravelerProfile,
        actor_user_id: str,
        updated_at: datetime,
    ) -> bool:
        ciphertext = self._encrypt_profile(profile)
        if expected_version == 0:
            result = cast(
                CursorResult[Any],
                await self.session.execute(
                    sqlite_insert(TravelerProfileRow)
                    .values(
                        membership_id=membership_id,
                        profile_ciphertext=ciphertext,
                        version=profile.version,
                        updated_by_user_id=actor_user_id,
                        created_at=updated_at,
                        updated_at=updated_at,
                    )
                    .on_conflict_do_nothing(index_elements=["membership_id"])
                ),
            )
            return result.rowcount == 1
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(TravelerProfileRow)
                .where(
                    TravelerProfileRow.membership_id == membership_id,
                    TravelerProfileRow.version == expected_version,
                )
                .values(
                    profile_ciphertext=ciphertext,
                    version=profile.version,
                    updated_by_user_id=actor_user_id,
                    updated_at=updated_at,
                )
            ),
        )
        return result.rowcount == 1

    async def set_role(self, membership_id: str, role: FamilyRole) -> None:
        await self.session.execute(
            update(FamilyMembershipRow)
            .where(FamilyMembershipRow.id == membership_id)
            .values(role=role.value)
        )

    async def remove_membership(self, membership_id: str) -> None:
        await self.session.execute(
            update(FamilyMembershipRow)
            .where(FamilyMembershipRow.id == membership_id)
            .values(status="removed")
        )

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

    def _member(
        self,
        membership: FamilyMembershipRow,
        user: UserRow,
        profile: TravelerProfileRow | None,
    ) -> FamilyMember:
        display_name = self._protector.decrypt(
            user.display_name_ciphertext, context="user.display_name"
        )
        return FamilyMember(
            membership_id=membership.id,
            family_id=membership.family_id,
            user=UserIdentity(
                id=user.id,
                username=user.username_normalized,
                email=user.email_normalized,
                display_name=display_name,
                system_role=SystemRole(user.system_role),
                status=UserStatus(user.status),
                session_epoch=user.session_epoch,
            ),
            role=FamilyRole(membership.role),
            joined_at=_aware(membership.joined_at),
            profile=(
                self._decrypt_profile(profile.profile_ciphertext, profile.version)
                if profile
                else _default_profile(display_name)
            ),
        )

    def _encrypt_profile(self, profile: TravelerProfile) -> bytes:
        payload = {
            "nickname": profile.nickname,
            "member_type": profile.member_type.value,
            "birth_year": profile.birth_year,
            "discount_eligibilities": profile.discount_eligibilities,
            "dietary_restrictions": profile.dietary_restrictions,
            "allergies": profile.allergies,
            "health_notes": profile.health_notes,
            "mobility_notes": profile.mobility_notes,
            "travel_preferences": profile.travel_preferences,
            "sensitive_visibility": profile.sensitive_visibility.value,
        }
        return self._protector.encrypt(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            context="traveler_profile.payload",
        )

    def _decrypt_profile(self, ciphertext: bytes, version: int) -> TravelerProfile:
        payload = json.loads(
            self._protector.decrypt(ciphertext, context="traveler_profile.payload")
        )
        return TravelerProfile(
            nickname=payload["nickname"],
            member_type=MemberType(payload["member_type"]),
            birth_year=payload["birth_year"],
            discount_eligibilities=tuple(payload["discount_eligibilities"]),
            dietary_restrictions=tuple(payload["dietary_restrictions"]),
            allergies=tuple(payload["allergies"]),
            health_notes=payload["health_notes"],
            mobility_notes=payload["mobility_notes"],
            travel_preferences=tuple(payload["travel_preferences"]),
            sensitive_visibility=SensitiveVisibility(payload["sensitive_visibility"]),
            version=version,
        )


def _default_profile(display_name: str) -> TravelerProfile:
    return TravelerProfile(
        nickname=display_name,
        member_type=MemberType.ADULT,
        birth_year=None,
        discount_eligibilities=(),
        dietary_restrictions=(),
        allergies=(),
        health_notes="",
        mobility_notes="",
        travel_preferences=(),
        sensitive_visibility=SensitiveVisibility.FAMILY,
        version=0,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
