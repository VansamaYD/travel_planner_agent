from __future__ import annotations

import hashlib
import hmac
import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from travel_agent.modules.access.application.errors import (
    AlreadyInitializedError,
    CsrfMismatchError,
    InvalidCredentialsError,
    InvalidInputError,
    PermissionDeniedError,
)
from travel_agent.modules.access.application.ports import (
    AccessStoreFactory,
    Clock,
    PasswordHasher,
    TokenIssuer,
)
from travel_agent.modules.access.domain.models import (
    AuthenticatedSession,
    FamilyRole,
    SystemRole,
)
from travel_agent.shared.domain.ids import new_uuid7


@dataclass(frozen=True, slots=True)
class SessionIssue:
    cookie_token: str
    session: AuthenticatedSession


@dataclass(frozen=True, slots=True)
class InitializationResult:
    recovery_code: str
    session_issue: SessionIssue


class AccessService:
    def __init__(
        self,
        store_factory: AccessStoreFactory,
        password_hasher: PasswordHasher,
        token_issuer: TokenIssuer,
        clock: Clock,
        session_lifetime: timedelta,
    ) -> None:
        self._store_factory = store_factory
        self._password_hasher = password_hasher
        self._token_issuer = token_issuer
        self._clock = clock
        self._session_lifetime = session_lifetime

    async def setup_status(self) -> bool:
        async with self._store_factory() as store:
            return await store.is_initialized()

    async def initialize(
        self,
        *,
        username: str,
        email: str | None,
        display_name: str,
        password: str,
        family_name: str,
        request_id: str | None,
    ) -> InitializationResult:
        normalized_username = _normalize_username(username)
        normalized_email = _normalize_email(email)
        clean_display_name = _required_text(display_name, "display_name", 1, 80)
        clean_family_name = _required_text(family_name, "family_name", 1, 80)
        _validate_password(password)

        now = self._clock.now()
        password_hash = await self._password_hasher.hash(password)
        recovery_code = self._token_issuer.recovery_code()
        recovery_hash = await self._password_hasher.hash(recovery_code)
        user_id = new_uuid7()
        family_id = new_uuid7()
        token = self._token_issuer.session_token()
        csrf = self._token_issuer.csrf_token()
        session_id = new_uuid7()
        expires_at = now + self._session_lifetime

        async with self._store_factory() as store:
            if not await store.claim_initialization(now, recovery_hash):
                raise AlreadyInitializedError
            user = await store.add_user(
                user_id=user_id,
                username=normalized_username,
                email=normalized_email,
                display_name=clean_display_name,
                password_hash=password_hash,
                system_role=SystemRole.ADMIN,
                created_at=now,
            )
            await store.add_family(
                family_id=family_id,
                name=clean_family_name,
                owner_user_id=user_id,
                created_at=now,
            )
            await store.add_membership(
                membership_id=new_uuid7(),
                family_id=family_id,
                user_id=user_id,
                role=FamilyRole.OWNER,
                joined_at=now,
            )
            await store.add_session(
                session_id=session_id,
                token_hash=_token_hash(token),
                csrf_token=csrf,
                user_id=user_id,
                session_epoch=user.session_epoch,
                created_at=now,
                expires_at=expires_at,
            )
            await store.add_audit(
                event_type="system.initialized",
                actor_user_id=user_id,
                subject_type="system",
                subject_id="primary",
                request_id=request_id,
                details={"family_id": family_id},
                created_at=now,
            )
            await store.commit()
        families = await self._families_for(user_id)
        return InitializationResult(
            recovery_code=recovery_code,
            session_issue=SessionIssue(
                cookie_token=token,
                session=AuthenticatedSession(session_id, user, csrf, expires_at, families),
            ),
        )

    async def login(self, *, login: str, password: str, request_id: str | None) -> SessionIssue:
        normalized_login = _normalize_login(login)
        now = self._clock.now()
        async with self._store_factory() as store:
            record = await store.find_user_by_login(normalized_login)
            valid = record is not None and await self._password_hasher.verify(
                record.password_hash, password
            )
            if not valid or record is None or record.identity.status.value != "active":
                await store.add_audit(
                    event_type="auth.login_failed",
                    actor_user_id=None,
                    subject_type="login_identifier",
                    subject_id=hashlib.sha256(normalized_login.encode()).hexdigest()[:16],
                    request_id=request_id,
                    details={},
                    created_at=now,
                )
                await store.commit()
                raise InvalidCredentialsError
            token = self._token_issuer.session_token()
            csrf = self._token_issuer.csrf_token()
            expires_at = now + self._session_lifetime
            session_id = new_uuid7()
            await store.mark_login(record.identity.id, now)
            await store.add_session(
                session_id=session_id,
                token_hash=_token_hash(token),
                csrf_token=csrf,
                user_id=record.identity.id,
                session_epoch=record.identity.session_epoch,
                created_at=now,
                expires_at=expires_at,
            )
            await store.add_audit(
                event_type="auth.login_succeeded",
                actor_user_id=record.identity.id,
                subject_type="session",
                subject_id=session_id,
                request_id=request_id,
                details={},
                created_at=now,
            )
            await store.commit()
        families = await self._families_for(record.identity.id)
        return SessionIssue(
            token,
            AuthenticatedSession(session_id, record.identity, csrf, expires_at, families),
        )

    async def authenticate(self, cookie_token: str | None) -> AuthenticatedSession | None:
        if not cookie_token:
            return None
        async with self._store_factory() as store:
            return await store.get_session(_token_hash(cookie_token), self._clock.now())

    async def logout(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        request_id: str | None,
    ) -> None:
        self.require_csrf(session, csrf_token)
        now = self._clock.now()
        async with self._store_factory() as store:
            await store.revoke_session(session.id, now)
            await store.add_audit(
                event_type="auth.logout",
                actor_user_id=session.user.id,
                subject_type="session",
                subject_id=session.id,
                request_id=request_id,
                details={},
                created_at=now,
            )
            await store.commit()

    async def create_family(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        name: str,
        request_id: str | None,
    ) -> str:
        self.require_csrf(session, csrf_token)
        if session.user.system_role is not SystemRole.ADMIN:
            raise PermissionDeniedError
        clean_name = _required_text(name, "name", 1, 80)
        family_id = new_uuid7()
        now = self._clock.now()
        async with self._store_factory() as store:
            await store.add_family(
                family_id=family_id,
                name=clean_name,
                owner_user_id=session.user.id,
                created_at=now,
            )
            await store.add_membership(
                membership_id=new_uuid7(),
                family_id=family_id,
                user_id=session.user.id,
                role=FamilyRole.OWNER,
                joined_at=now,
            )
            await store.add_audit(
                event_type="family.created",
                actor_user_id=session.user.id,
                subject_type="family",
                subject_id=family_id,
                request_id=request_id,
                details={},
                created_at=now,
            )
            await store.commit()
        return family_id

    @staticmethod
    def require_csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        if not supplied or not hmac.compare_digest(session.csrf_token, supplied):
            raise CsrfMismatchError

    async def _families_for(self, user_id: str):  # type: ignore[no-untyped-def]
        async with self._store_factory() as store:
            return await store.list_families(user_id)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_login(value: str) -> str:
    candidate = unicodedata.normalize("NFKC", value).strip().casefold()
    if not candidate or len(candidate) > 320:
        raise InvalidInputError("invalid login")
    return candidate


def _normalize_username(value: str) -> str:
    candidate = _normalize_login(value)
    if not 3 <= len(candidate) <= 64:
        raise InvalidInputError("username must contain 3 to 64 characters")
    if not all(character.isalnum() or character in "._-" for character in candidate):
        raise InvalidInputError("username contains unsupported characters")
    return candidate


def _normalize_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    candidate = _normalize_login(value)
    local, separator, domain = candidate.partition("@")
    if not separator or not local or "." not in domain or domain.startswith("."):
        raise InvalidInputError("invalid email")
    return candidate


def _required_text(value: str, field: str, minimum: int, maximum: int) -> str:
    candidate = unicodedata.normalize("NFKC", value).strip()
    if not minimum <= len(candidate) <= maximum:
        raise InvalidInputError(f"{field} length is invalid")
    return candidate


def _validate_password(password: str) -> None:
    if not 10 <= len(password) <= 256:
        raise InvalidInputError("password must contain 10 to 256 characters")
