from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass, replace
from datetime import date

from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.trips.application.errors import (
    TripInvalidInputError,
    TripNotFoundError,
    TripPermissionDeniedError,
    TripVersionConflictError,
)
from travel_agent.modules.trips.application.ports import Clock, TripStoreFactory
from travel_agent.modules.trips.domain.models import (
    TripDraft,
    TripInputMode,
    TripParticipant,
    TripRequirements,
    TripStatus,
    TripVersion,
    TripVisibility,
)
from travel_agent.shared.domain.ids import new_uuid7


@dataclass(frozen=True, slots=True)
class RequirementsInput:
    input_mode: str = "form"
    origin: str = ""
    destinations: tuple[str, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    budget_cents: int | None = None
    currency: str = "CNY"
    styles: tuple[str, ...] = ()
    pace: str = "balanced"
    transportation: tuple[str, ...] = ()
    hard_constraints: tuple[str, ...] = ()
    soft_preferences: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    source_text: str = ""
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class CreateTripInput:
    family_id: str
    title: str
    visibility: str
    requirements: RequirementsInput
    membership_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UpdateTripInput:
    expected_version: int
    title: str
    visibility: str
    requirements: RequirementsInput
    membership_ids: tuple[str, ...]


class TripService:
    def __init__(self, store_factory: TripStoreFactory, clock: Clock) -> None:
        self._store_factory = store_factory
        self._clock = clock

    async def create(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        data: CreateTripInput,
        request_id: str | None,
    ) -> TripDraft:
        self._require_csrf(session, csrf_token)
        requirements = self._requirements(data.requirements)
        now = self._clock.now()
        async with self._store_factory() as store:
            role = await store.actor_role(data.family_id, session.user.id)
            if role not in {"owner", "admin", "member"}:
                raise TripPermissionDeniedError
            snapshots = await store.participant_snapshots(data.family_id, data.membership_ids)
            if len(snapshots) != len(set(data.membership_ids)):
                raise TripInvalidInputError("部分参与者不属于当前家庭。")
            participants = tuple(self._participant(item) for item in snapshots)
            draft = TripDraft(
                id=new_uuid7(),
                family_id=data.family_id,
                owner_user_id=session.user.id,
                title=self._text(data.title, "旅行名称", 80),
                status=TripStatus.DRAFT,
                visibility=self._visibility(data.visibility),
                version=1,
                requirements=requirements,
                participants=participants,
                warnings=self._warnings(requirements, len(participants)),
                created_at=now,
                updated_at=now,
            )
            await store.create(draft, session.user.id, request_id)
            await store.commit()
            return draft

    async def list(self, session: AuthenticatedSession, family_id: str | None):
        async with self._store_factory() as store:
            if family_id and await store.actor_role(family_id, session.user.id) is None:
                raise TripPermissionDeniedError
            return await store.list_visible(session.user.id, family_id)

    async def deleted(self, session: AuthenticatedSession, family_id: str | None):
        async with self._store_factory() as store:
            if family_id:
                role = await store.actor_role(family_id, session.user.id)
                if role not in {"owner", "admin", "member"}:
                    raise TripPermissionDeniedError
            return await store.list_deleted(session.user.id, family_id)

    async def get(self, session: AuthenticatedSession, trip_id: str) -> TripDraft:
        async with self._store_factory() as store:
            draft = await self._load_visible(store, session.user.id, trip_id)
            return draft

    async def update(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        trip_id: str,
        data: UpdateTripInput,
        request_id: str | None,
    ) -> TripDraft:
        self._require_csrf(session, csrf_token)
        requirements = self._requirements(data.requirements)
        async with self._store_factory() as store:
            current = await self._load_visible(store, session.user.id, trip_id)
            role = await store.actor_role(current.family_id, session.user.id)
            if current.owner_user_id != session.user.id and role not in {"owner", "admin"}:
                raise TripPermissionDeniedError
            snapshots = await store.participant_snapshots(current.family_id, data.membership_ids)
            if len(snapshots) != len(set(data.membership_ids)):
                raise TripInvalidInputError("部分参与者不属于当前家庭。")
            participants = tuple(self._participant(item) for item in snapshots)
            updated = replace(
                current,
                title=self._text(data.title, "旅行名称", 80),
                visibility=self._visibility(data.visibility),
                version=data.expected_version + 1,
                requirements=requirements,
                participants=participants,
                warnings=self._warnings(requirements, len(participants)),
                updated_at=self._clock.now(),
            )
            changed = await store.update(
                updated,
                data.expected_version,
                "user_edit",
                "用户更新了旅行需求或参与者",
                session.user.id,
                request_id,
            )
            if not changed:
                raise TripVersionConflictError
            await store.commit()
            return updated

    async def versions(
        self, session: AuthenticatedSession, trip_id: str
    ) -> tuple[TripVersion, ...]:
        async with self._store_factory() as store:
            await self._load_visible(store, session.user.id, trip_id)
            return await store.list_versions(trip_id)

    async def version(
        self, session: AuthenticatedSession, trip_id: str, version_no: int
    ) -> TripVersion:
        async with self._store_factory() as store:
            await self._load_visible(store, session.user.id, trip_id)
            version = await store.get_version(trip_id, version_no)
            if version is None:
                raise TripNotFoundError
            return version

    async def delete(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        trip_id: str,
        request_id: str | None,
    ) -> None:
        self._require_csrf(session, csrf_token)
        async with self._store_factory() as store:
            loaded = await store.get_including_deleted(trip_id)
            if loaded is None:
                raise TripNotFoundError
            draft, is_deleted = loaded
            if is_deleted:
                return
            role = await store.actor_role(draft.family_id, session.user.id)
            if draft.owner_user_id != session.user.id and role not in {"owner", "admin"}:
                raise TripPermissionDeniedError
            changed = await store.set_deleted(
                trip_id,
                deleted=True,
                actor_user_id=session.user.id,
                request_id=request_id,
                changed_at=self._clock.now(),
            )
            if not changed:
                raise TripVersionConflictError
            await store.commit()

    async def restore(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        trip_id: str,
        request_id: str | None,
    ) -> TripDraft:
        self._require_csrf(session, csrf_token)
        async with self._store_factory() as store:
            loaded = await store.get_including_deleted(trip_id)
            if loaded is None:
                raise TripNotFoundError
            draft, is_deleted = loaded
            role = await store.actor_role(draft.family_id, session.user.id)
            if draft.owner_user_id != session.user.id and role not in {"owner", "admin"}:
                raise TripPermissionDeniedError
            if is_deleted:
                changed = await store.set_deleted(
                    trip_id,
                    deleted=False,
                    actor_user_id=session.user.id,
                    request_id=request_id,
                    changed_at=self._clock.now(),
                )
                if not changed:
                    raise TripVersionConflictError
                await store.commit()
            return draft

    @staticmethod
    async def _load_visible(store, user_id: str, trip_id: str) -> TripDraft:
        draft = await store.get(trip_id)
        if draft is None:
            raise TripNotFoundError
        role = await store.actor_role(draft.family_id, user_id)
        if draft.owner_user_id != user_id and (
            draft.visibility is TripVisibility.PRIVATE or role is None
        ):
            raise TripPermissionDeniedError
        return draft

    def _requirements(self, data: RequirementsInput) -> TripRequirements:
        try:
            input_mode = TripInputMode(data.input_mode)
        except ValueError as error:
            raise TripInvalidInputError("不支持的需求输入方式。") from error
        if data.start_date and data.end_date and data.end_date < data.start_date:
            raise TripInvalidInputError("结束日期不能早于开始日期。")
        if data.budget_cents is not None and data.budget_cents < 0:
            raise TripInvalidInputError("预算不能为负数。")
        destinations = self._items(data.destinations, 50)
        if input_mode is TripInputMode.FORM and not destinations:
            raise TripInvalidInputError("请至少填写一个目的地。")
        return TripRequirements(
            input_mode=input_mode,
            origin=self._optional_text(data.origin, 120),
            destinations=destinations,
            start_date=data.start_date,
            end_date=data.end_date,
            budget_cents=data.budget_cents,
            currency=data.currency.upper(),
            styles=self._items(data.styles, 20),
            pace=data.pace,
            transportation=self._items(data.transportation, 20),
            hard_constraints=self._items(data.hard_constraints, 30),
            soft_preferences=self._items(data.soft_preferences, 30),
            assumptions=self._items(data.assumptions, 30),
            source_text=self._optional_text(data.source_text, 8000),
            confirmed=data.confirmed,
        )

    @staticmethod
    def _participant(item: dict[str, object]) -> TripParticipant:
        birth_year = item.get("birth_year")

        def strings(key: str) -> tuple[str, ...]:
            value = item.get(key)
            if not isinstance(value, (list, tuple)):
                return ()
            return tuple(str(entry) for entry in value)

        return TripParticipant(
            id=new_uuid7(),
            source_membership_id=str(item["membership_id"]),
            display_name=str(item["display_name"]),
            member_type=str(item["member_type"]),
            birth_year=birth_year if isinstance(birth_year, int) else None,
            discount_eligibilities=strings("discount_eligibilities"),
            dietary_restrictions=strings("dietary_restrictions"),
            allergies=strings("allergies"),
            health_notes=str(item.get("health_notes", "")),
            mobility_notes=str(item.get("mobility_notes", "")),
            travel_preferences=strings("travel_preferences"),
            is_temporary=False,
        )

    @staticmethod
    def _warnings(requirements: TripRequirements, people: int) -> tuple[str, ...]:
        warnings: list[str] = []
        if people > 10:
            warnings.append("参与者超过 10 人，后续交通和餐饮报价可能需要分组核验。")  # noqa: RUF001
        if len(requirements.destinations) > 10:
            warnings.append("目的地超过 10 个，建议确认行程节奏和跨城时间。")  # noqa: RUF001
        if (
            requirements.start_date
            and requirements.end_date
            and (requirements.end_date - requirements.start_date).days + 1 > 30
        ):
            warnings.append(
                "行程超过 30 天，建议拆分阶段生成以控制模型上下文和外部查询费用。"  # noqa: RUF001
            )
        if not requirements.confirmed:
            warnings.append("需求尚未确认；智能体生成正式计划前需要再次确认硬性约束。")  # noqa: RUF001
        return tuple(warnings)

    @staticmethod
    def _visibility(value: str) -> TripVisibility:
        try:
            return TripVisibility(value)
        except ValueError as error:
            raise TripInvalidInputError("不支持的可见范围。") from error

    @staticmethod
    def _text(value: str, label: str, maximum: int) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            raise TripInvalidInputError(f"{label}不能为空。")
        if len(normalized) > maximum:
            raise TripInvalidInputError(f"{label}过长。")
        return normalized

    @classmethod
    def _optional_text(cls, value: str, maximum: int) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if len(normalized) > maximum:
            raise TripInvalidInputError("输入内容过长。")
        return normalized

    @classmethod
    def _items(cls, values: tuple[str, ...], limit: int) -> tuple[str, ...]:
        if len(values) > limit:
            raise TripInvalidInputError("列表项目过多。")
        return tuple(
            dict.fromkeys(item for value in values if (item := cls._optional_text(value, 120)))
        )

    @staticmethod
    def _require_csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
            raise TripPermissionDeniedError
