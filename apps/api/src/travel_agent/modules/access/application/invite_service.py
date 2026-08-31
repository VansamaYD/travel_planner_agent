from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from travel_agent.modules.access.application.errors import (
    InvalidInputError,
    InvalidInviteError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from travel_agent.modules.access.application.invite_ports import InviteStore, InviteStoreFactory
from travel_agent.modules.access.application.ports import Clock, PasswordHasher, TokenIssuer
from travel_agent.modules.access.application.service import (
    AccessService,
    _normalize_email,
    _normalize_username,
    _required_text,
    _validate_password,
)
from travel_agent.modules.access.domain.models import AuthenticatedSession, FamilyInvite, FamilyRole
from travel_agent.shared.domain.ids import new_uuid7


@dataclass(frozen=True, slots=True)
class InvitationIssue:
    invite: FamilyInvite
    code: str


class FamilyInviteService:
    def __init__(
        self,
        store_factory: InviteStoreFactory,
        token_issuer: TokenIssuer,
        password_hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._store_factory = store_factory
        self._token_issuer = token_issuer
        self._password_hasher = password_hasher
        self._clock = clock

    async def create_invite(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        role: str,
        expires_in_days: int,
        request_id: str | None,
    ) -> InvitationIssue:
        AccessService.require_csrf(session, csrf_token)
        requested_role = _invite_role(role)
        if not 1 <= expires_in_days <= 30:
            raise InvalidInputError("expires_in_days must be between 1 and 30")
        now = self._clock.now()
        expires_at = now + timedelta(days=expires_in_days)
        code = self._token_issuer.invite_code()
        invite = FamilyInvite(
            id=new_uuid7(),
            family_id=family_id,
            role=requested_role,
            status="active",
            created_by_user_id=session.user.id,
            created_at=now,
            expires_at=expires_at,
            accepted_by_user_id=None,
        )
        async with self._store_factory() as store:
            actor_role = await self._require_manager(store, family_id, session.user.id)
            if requested_role is FamilyRole.ADMIN and actor_role is not FamilyRole.OWNER:
                raise PermissionDeniedError
            await store.add_invite(
                invite_id=invite.id,
                family_id=family_id,
                token_hash=_code_hash(code),
                role=requested_role,
                created_by_user_id=session.user.id,
                created_at=now,
                expires_at=expires_at,
            )
            await store.add_audit(
                event_type="family.invite_created",
                actor_user_id=session.user.id,
                subject_type="family_invite",
                subject_id=invite.id,
                request_id=request_id,
                details={
                    "family_id": family_id,
                    "role": requested_role.value,
                    "expires_at": expires_at.isoformat(),
                },
                created_at=now,
            )
            await store.commit()
        return InvitationIssue(invite=invite, code=code)

    async def list_invites(
        self, session: AuthenticatedSession, family_id: str
    ) -> tuple[FamilyInvite, ...]:
        now = self._clock.now()
        async with self._store_factory() as store:
            await self._require_manager(store, family_id, session.user.id)
            return await store.list_invites(family_id, now)

    async def revoke_invite(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        family_id: str,
        invite_id: str,
        request_id: str | None,
    ) -> None:
        AccessService.require_csrf(session, csrf_token)
        now = self._clock.now()
        async with self._store_factory() as store:
            await self._require_manager(store, family_id, session.user.id)
            if not await store.revoke_invite(family_id, invite_id, now):
                raise ResourceNotFoundError
            await store.add_audit(
                event_type="family.invite_revoked",
                actor_user_id=session.user.id,
                subject_type="family_invite",
                subject_id=invite_id,
                request_id=request_id,
                details={"family_id": family_id},
                created_at=now,
            )
            await store.commit()

    async def accept_invite(
        self,
        *,
        session: AuthenticatedSession,
        csrf_token: str | None,
        code: str,
        request_id: str | None,
    ) -> str:
        AccessService.require_csrf(session, csrf_token)
        normalized_code = _normalize_code(code)
        now = self._clock.now()
        async with self._store_factory() as store:
            invite = await store.find_invite(_code_hash(normalized_code), now)
            if invite is None:
                raise InvalidInviteError
            if await store.has_active_membership(invite.family_id, session.user.id):
                raise ResourceConflictError
            if not await store.claim_invite(invite.id, session.user.id, now):
                raise InvalidInviteError
            await store.activate_membership(
                membership_id=new_uuid7(),
                family_id=invite.family_id,
                user_id=session.user.id,
                role=invite.role,
                joined_at=now,
            )
            await store.add_audit(
                event_type="family.invite_accepted",
                actor_user_id=session.user.id,
                subject_type="family_invite",
                subject_id=invite.id,
                request_id=request_id,
                details={"family_id": invite.family_id, "role": invite.role.value},
                created_at=now,
            )
            await store.commit()
        return invite.family_id

    async def register_with_invite(
        self,
        *,
        code: str,
        username: str,
        email: str | None,
        display_name: str,
        password: str,
        request_id: str | None,
    ) -> str:
        normalized_code = _normalize_code(code)
        normalized_username = _normalize_username(username)
        normalized_email = _normalize_email(email)
        clean_display_name = _required_text(display_name, "display_name", 1, 80)
        _validate_password(password)
        now = self._clock.now()
        async with self._store_factory() as store:
            invite = await store.find_invite(_code_hash(normalized_code), now)
            if invite is None:
                raise InvalidInviteError
            if await store.login_exists(normalized_username, normalized_email):
                raise ResourceConflictError
            password_hash = await self._password_hasher.hash(password)
            user_id = new_uuid7()
            if not await store.add_invited_user(
                user_id=user_id,
                username=normalized_username,
                email=normalized_email,
                display_name=clean_display_name,
                password_hash=password_hash,
                created_at=now,
            ):
                raise ResourceConflictError
            if not await store.claim_invite(invite.id, user_id, now):
                raise InvalidInviteError
            await store.activate_membership(
                membership_id=new_uuid7(),
                family_id=invite.family_id,
                user_id=user_id,
                role=invite.role,
                joined_at=now,
            )
            await store.add_audit(
                event_type="family.invite_registered",
                actor_user_id=user_id,
                subject_type="family_invite",
                subject_id=invite.id,
                request_id=request_id,
                details={"family_id": invite.family_id, "role": invite.role.value},
                created_at=now,
            )
            await store.commit()
        return normalized_username

    @staticmethod
    async def _require_manager(store: InviteStore, family_id: str, user_id: str) -> FamilyRole:
        role = await store.actor_role(family_id, user_id)
        if role not in (FamilyRole.OWNER, FamilyRole.ADMIN):
            raise PermissionDeniedError
        return role


def _normalize_code(code: str) -> str:
    normalized = "".join(character for character in code.upper().strip() if character != "-")
    if not 20 <= len(normalized) <= 40 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in normalized
    ):
        raise InvalidInviteError
    return normalized


def _code_hash(code: str) -> str:
    return hashlib.sha256(_normalize_code(code).encode("ascii")).hexdigest()


def _invite_role(value: str) -> FamilyRole:
    try:
        role = FamilyRole(value)
    except ValueError as error:
        raise InvalidInputError("invalid invite role") from error
    if role is FamilyRole.OWNER:
        raise InvalidInputError("family ownership cannot be invited")
    return role
