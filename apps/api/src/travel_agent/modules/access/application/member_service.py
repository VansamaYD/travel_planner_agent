from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

from travel_agent.modules.access.application.errors import (
    InvalidInputError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceNotFoundError,
    VersionConflictError,
)
from travel_agent.modules.access.application.member_ports import MemberStore, MemberStoreFactory
from travel_agent.modules.access.application.ports import Clock, PasswordHasher
from travel_agent.modules.access.application.service import (
    _normalize_email,
    _normalize_username,
    _required_text,
    _validate_password,
)
from travel_agent.modules.access.domain.models import (
    AuthenticatedSession,
    FamilyMember,
    FamilyRole,
    MemberType,
    SensitiveVisibility,
    TravelerProfile,
    UserIdentity,
)
from travel_agent.shared.domain.ids import new_uuid7


@dataclass(frozen=True, slots=True)
class ProfileInput:
    nickname: str
    member_type: str
    birth_year: int | None
    discount_eligibilities: tuple[str, ...]
    dietary_restrictions: tuple[str, ...]
    allergies: tuple[str, ...]
    health_notes: str
    mobility_notes: str
    travel_preferences: tuple[str, ...]
    sensitive_visibility: str


class FamilyMemberService:
    def __init__(
        self,
        store_factory: MemberStoreFactory,
        password_hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._store_factory = store_factory
        self._password_hasher = password_hasher
        self._clock = clock

    async def list_members(
        self, session: AuthenticatedSession, family_id: str
    ) -> tuple[FamilyMember, ...]:
        async with self._store_factory() as store:
            actor_role = await self._require_family_role(store, family_id, session.user.id)
            members = await store.list_members(family_id)
        return tuple(
            self._redact(
                member,
                session.user.id,
                actor_role in (FamilyRole.OWNER, FamilyRole.ADMIN),
            )
            for member in members
        )

    async def create_member(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        username: str,
        email: str | None,
        display_name: str,
        password: str,
        role: str,
        profile_input: ProfileInput,
        request_id: str | None,
    ) -> str:
        self._require_csrf(session, csrf_token)
        normalized_username = _normalize_username(username)
        normalized_email = _normalize_email(email)
        clean_display_name = _required_text(display_name, "display_name", 1, 80)
        _validate_password(password)
        requested_role = _editable_role(role)
        profile = _profile(profile_input, version=1, fallback_name=clean_display_name)
        user_id, membership_id, now = new_uuid7(), new_uuid7(), self._clock.now()
        async with self._store_factory() as store:
            actor_role = await self._require_manager(store, family_id, session.user.id)
            if requested_role is FamilyRole.ADMIN and actor_role is not FamilyRole.OWNER:
                raise PermissionDeniedError
            if await store.login_exists(normalized_username, normalized_email):
                raise ResourceConflictError
            password_hash = await self._password_hasher.hash(password)
            created = await store.create_member(
                family_id=family_id,
                user_id=user_id,
                membership_id=membership_id,
                username=normalized_username,
                email=normalized_email,
                display_name=clean_display_name,
                password_hash=password_hash,
                role=requested_role,
                profile=profile,
                actor_user_id=session.user.id,
                created_at=now,
            )
            if not created:
                raise ResourceConflictError
            await store.add_audit(
                event_type="family.member_created",
                actor_user_id=session.user.id,
                subject_type="family_membership",
                subject_id=membership_id,
                request_id=request_id,
                details={"family_id": family_id, "role": requested_role.value},
                created_at=now,
            )
            await store.commit()
        return membership_id

    async def update_profile(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        membership_id: str,
        expected_version: int,
        profile_input: ProfileInput,
        request_id: str | None,
    ) -> TravelerProfile:
        self._require_csrf(session, csrf_token)
        now = self._clock.now()
        async with self._store_factory() as store:
            actor_role = await self._require_family_role(store, family_id, session.user.id)
            member = await store.get_member(family_id, membership_id)
            if member is None:
                raise ResourceNotFoundError
            is_self = member.user.id == session.user.id
            if not is_self and actor_role not in (FamilyRole.OWNER, FamilyRole.ADMIN):
                raise PermissionDeniedError
            if not is_self and (member.profile.sensitive_visibility is SensitiveVisibility.PRIVATE):
                profile_input = ProfileInput(
                    nickname=profile_input.nickname,
                    member_type=profile_input.member_type,
                    birth_year=profile_input.birth_year,
                    discount_eligibilities=profile_input.discount_eligibilities,
                    dietary_restrictions=profile_input.dietary_restrictions,
                    allergies=member.profile.allergies,
                    health_notes=member.profile.health_notes,
                    mobility_notes=member.profile.mobility_notes,
                    travel_preferences=profile_input.travel_preferences,
                    sensitive_visibility=member.profile.sensitive_visibility.value,
                )
            updated = _profile(
                profile_input,
                version=expected_version + 1,
                fallback_name=member.user.display_name,
            )
            saved = await store.save_profile(
                membership_id=membership_id,
                expected_version=expected_version,
                profile=updated,
                actor_user_id=session.user.id,
                updated_at=now,
            )
            if not saved:
                raise VersionConflictError
            await store.add_audit(
                event_type="traveler_profile.updated",
                actor_user_id=session.user.id,
                subject_type="traveler_profile",
                subject_id=membership_id,
                request_id=request_id,
                details={"from_version": expected_version, "to_version": updated.version},
                created_at=now,
            )
            await store.commit()
        return self._redact_profile(updated, member.user.id, session.user.id)

    async def change_role(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        membership_id: str,
        role: str,
        request_id: str | None,
    ) -> None:
        self._require_csrf(session, csrf_token)
        requested_role, now = _editable_role(role), self._clock.now()
        async with self._store_factory() as store:
            actor_role = await self._require_manager(store, family_id, session.user.id)
            member = await store.get_member(family_id, membership_id)
            if member is None:
                raise ResourceNotFoundError
            if member.role is FamilyRole.OWNER or member.user.id == session.user.id:
                raise PermissionDeniedError
            if (member.role is FamilyRole.ADMIN or requested_role is FamilyRole.ADMIN) and (
                actor_role is not FamilyRole.OWNER
            ):
                raise PermissionDeniedError
            await store.set_role(membership_id, requested_role)
            await store.add_audit(
                event_type="family.member_role_changed",
                actor_user_id=session.user.id,
                subject_type="family_membership",
                subject_id=membership_id,
                request_id=request_id,
                details={"from": member.role.value, "to": requested_role.value},
                created_at=now,
            )
            await store.commit()

    async def remove_member(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        membership_id: str,
        request_id: str | None,
    ) -> None:
        self._require_csrf(session, csrf_token)
        now = self._clock.now()
        async with self._store_factory() as store:
            actor_role = await self._require_manager(store, family_id, session.user.id)
            member = await store.get_member(family_id, membership_id)
            if member is None:
                raise ResourceNotFoundError
            if member.role is FamilyRole.OWNER or member.user.id == session.user.id:
                raise PermissionDeniedError
            if member.role is FamilyRole.ADMIN and actor_role is not FamilyRole.OWNER:
                raise PermissionDeniedError
            await store.remove_membership(membership_id)
            await store.add_audit(
                event_type="family.member_removed",
                actor_user_id=session.user.id,
                subject_type="family_membership",
                subject_id=membership_id,
                request_id=request_id,
                details={"family_id": family_id},
                created_at=now,
            )
            await store.commit()

    @staticmethod
    async def _require_family_role(store: MemberStore, family_id: str, user_id: str) -> FamilyRole:
        role = await store.actor_role(family_id, user_id)
        if role is None:
            raise PermissionDeniedError
        return role

    async def _require_manager(
        self, store: MemberStore, family_id: str, user_id: str
    ) -> FamilyRole:
        role = await self._require_family_role(store, family_id, user_id)
        if role not in (FamilyRole.OWNER, FamilyRole.ADMIN):
            raise PermissionDeniedError
        return role

    @staticmethod
    def _require_csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        from travel_agent.modules.access.application.service import AccessService

        AccessService.require_csrf(session, supplied)

    def _redact(self, member: FamilyMember, actor_user_id: str, can_manage: bool) -> FamilyMember:
        is_self = member.user.id == actor_user_id
        return FamilyMember(
            membership_id=member.membership_id,
            family_id=member.family_id,
            user=(
                member.user
                if is_self or can_manage
                else UserIdentity(
                    id=member.user.id,
                    username="",
                    email=None,
                    display_name=member.user.display_name,
                    system_role=member.user.system_role,
                    status=member.user.status,
                    session_epoch=member.user.session_epoch,
                )
            ),
            role=member.role,
            joined_at=member.joined_at,
            profile=self._redact_profile(member.profile, member.user.id, actor_user_id),
        )

    @staticmethod
    def _redact_profile(
        profile: TravelerProfile, profile_user_id: str, actor_user_id: str
    ) -> TravelerProfile:
        if (
            profile.sensitive_visibility is SensitiveVisibility.FAMILY
            or profile_user_id == actor_user_id
        ):
            return profile
        return TravelerProfile(
            nickname=profile.nickname,
            member_type=profile.member_type,
            birth_year=profile.birth_year,
            discount_eligibilities=profile.discount_eligibilities,
            dietary_restrictions=profile.dietary_restrictions,
            allergies=(),
            health_notes="",
            mobility_notes="",
            travel_preferences=profile.travel_preferences,
            sensitive_visibility=profile.sensitive_visibility,
            version=profile.version,
        )


def _profile(value: ProfileInput, *, version: int, fallback_name: str) -> TravelerProfile:
    try:
        member_type = MemberType(value.member_type)
        visibility = SensitiveVisibility(value.sensitive_visibility)
    except ValueError as error:
        raise InvalidInputError("invalid member type or visibility") from error
    current_year = datetime.now().year
    if value.birth_year is not None and not current_year - 120 <= value.birth_year <= current_year:
        raise InvalidInputError("birth_year is outside the supported range")
    return TravelerProfile(
        nickname=_required_text(value.nickname or fallback_name, "nickname", 1, 80),
        member_type=member_type,
        birth_year=value.birth_year,
        discount_eligibilities=_text_list(value.discount_eligibilities),
        dietary_restrictions=_text_list(value.dietary_restrictions),
        allergies=_text_list(value.allergies),
        health_notes=_optional_text(value.health_notes, 500),
        mobility_notes=_optional_text(value.mobility_notes, 500),
        travel_preferences=_text_list(value.travel_preferences),
        sensitive_visibility=visibility,
        version=version,
    )


def _editable_role(value: str) -> FamilyRole:
    try:
        role = FamilyRole(value)
    except ValueError as error:
        raise InvalidInputError("invalid family role") from error
    if role is FamilyRole.OWNER:
        raise InvalidInputError("family ownership cannot be assigned here")
    return role


def _text_list(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) > 30:
        raise InvalidInputError("too many profile values")
    normalized = tuple(_optional_text(value, 80) for value in values if value.strip())
    return tuple(dict.fromkeys(normalized))


def _optional_text(value: str, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if len(normalized) > maximum:
        raise InvalidInputError("profile text is too long")
    return normalized
