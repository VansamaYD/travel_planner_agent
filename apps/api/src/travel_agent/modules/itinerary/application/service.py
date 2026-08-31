from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, timedelta

from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.itinerary.application.errors import (
    ItineraryInvalidInputError,
    ItineraryNotFoundError,
    ItineraryPermissionDeniedError,
    ItineraryVersionConflictError,
)
from travel_agent.modules.itinerary.application.ports import (
    Clock,
    ItineraryStore,
    ItineraryStoreFactory,
)
from travel_agent.modules.itinerary.domain.models import (
    ItineraryDay,
    ItineraryItem,
    ItineraryPlan,
    ItineraryVersionSummary,
)
from travel_agent.shared.domain.ids import new_uuid7


@dataclass(frozen=True, slots=True)
class ItemInput:
    logical_id: str | None
    item_type: str
    title: str
    place_name: str
    start_time: str | None
    end_time: str | None
    cost_cents: int | None
    execution_status: str
    notes: str
    tags: tuple[str, ...]
    transport_to_next: str | None
    travel_minutes_to_next: int | None
    travel_cost_cents_to_next: int | None


@dataclass(frozen=True, slots=True)
class DayInput:
    id: str | None
    local_date: date
    city: str
    summary: str
    items: tuple[ItemInput, ...]


class ItineraryService:
    def __init__(self, store_factory: ItineraryStoreFactory, clock: Clock) -> None:
        self._store_factory = store_factory
        self._clock = clock

    async def get(self, session: AuthenticatedSession, trip_id: str) -> ItineraryPlan:
        async with self._store_factory() as store:
            await self._authorize(store, session.user.id, trip_id, write=False)
            plan = await store.current(trip_id)
            if plan is None:
                raise ItineraryNotFoundError
            return plan

    async def initialize(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        trip_id: str,
        request_id: str | None,
    ) -> ItineraryPlan:
        self._csrf(session, csrf_token)
        async with self._store_factory() as store:
            context = await self._authorize(store, session.user.id, trip_id, write=True)
            existing = await store.current(trip_id)
            if existing is not None:
                return existing
            start_date = context.get("start_date")
            end_date = context.get("end_date")
            if not isinstance(start_date, date) or not isinstance(end_date, date):
                raise ItineraryInvalidInputError("请先在旅行需求中填写完整的开始和结束日期。")
            if (end_date - start_date).days > 60:
                raise ItineraryInvalidInputError("首版单次日程最多支持 60 天。")
            destinations = context.get("destinations")
            cities = (
                tuple(str(value) for value in destinations)
                if isinstance(destinations, list)
                else ()
            )
            days: list[ItineraryDay] = []
            current_date = start_date
            index = 0
            while current_date <= end_date:
                city = (
                    cities[
                        min(
                            index * len(cities) // max((end_date - start_date).days + 1, 1),
                            len(cities) - 1,
                        )
                    ]
                    if cities
                    else "待定城市"
                )
                days.append(
                    ItineraryDay(
                        id=new_uuid7(), local_date=current_date, city=city, summary="", items=()
                    )
                )
                current_date += timedelta(days=1)
                index += 1
            now = self._clock.now()
            plan = ItineraryPlan(
                id=new_uuid7(),
                trip_id=trip_id,
                version=1,
                days=tuple(days),
                currency="CNY",
                estimated_total_cost_cents=0,
                warnings=(
                    "当前为日程结构草稿；地点营业时间、路线和价格尚待智能体联网核验。",  # noqa: RUF001
                ),
                created_by_user_id=session.user.id,
                created_at=now,
            )
            await store.create(plan, "初始化按天旅行计划", request_id)
            await store.commit()
            return plan

    async def update(
        self,
        session: AuthenticatedSession,
        csrf_token: str | None,
        trip_id: str,
        expected_version: int,
        days: tuple[DayInput, ...],
        request_id: str | None,
    ) -> ItineraryPlan:
        self._csrf(session, csrf_token)
        async with self._store_factory() as store:
            await self._authorize(store, session.user.id, trip_id, write=True)
            current = await store.current(trip_id)
            if current is None:
                raise ItineraryNotFoundError
            normalized_days = self._days(days)
            total = sum(
                (item.cost_cents or 0) + (item.travel_cost_cents_to_next or 0)
                for day in normalized_days
                for item in day.items
            )
            updated = ItineraryPlan(
                id=new_uuid7(),
                trip_id=trip_id,
                version=expected_version + 1,
                days=normalized_days,
                currency=current.currency,
                estimated_total_cost_cents=total,
                warnings=current.warnings,
                created_by_user_id=session.user.id,
                created_at=self._clock.now(),
            )
            if not await store.update(updated, expected_version, "用户编辑日程模块", request_id):
                raise ItineraryVersionConflictError
            await store.commit()
            return updated

    async def versions(
        self, session: AuthenticatedSession, trip_id: str
    ) -> tuple[ItineraryVersionSummary, ...]:
        async with self._store_factory() as store:
            await self._authorize(store, session.user.id, trip_id, write=False)
            return await store.versions(trip_id)

    async def _authorize(
        self, store: ItineraryStore, user_id: str, trip_id: str, *, write: bool
    ) -> dict[str, object]:
        context = await store.trip_context(trip_id)
        if context is None:
            raise ItineraryNotFoundError
        family_id = str(context["family_id"])
        role = await store.actor_role(family_id, user_id)
        owner_user_id = str(context["owner_user_id"])
        visibility = str(context["visibility"])
        if write and owner_user_id != user_id and role not in {"owner", "admin"}:
            raise ItineraryPermissionDeniedError
        if not write and owner_user_id != user_id and (visibility == "private" or role is None):
            raise ItineraryPermissionDeniedError
        return context

    @staticmethod
    def _days(values: tuple[DayInput, ...]) -> tuple[ItineraryDay, ...]:
        if not values or len(values) > 60:
            raise ItineraryInvalidInputError("旅行计划必须包含 1 至 60 天。")
        seen_dates: set[date] = set()
        days: list[ItineraryDay] = []
        for value in sorted(values, key=lambda item: item.local_date):
            if value.local_date in seen_dates:
                raise ItineraryInvalidInputError("同一日期不能重复。")
            seen_dates.add(value.local_date)
            items = tuple(
                ItineraryItem(
                    logical_id=item.logical_id or new_uuid7(),
                    item_type=item.item_type,
                    title=item.title.strip(),
                    place_name=item.place_name.strip(),
                    start_time=item.start_time,
                    end_time=item.end_time,
                    cost_cents=item.cost_cents,
                    execution_status=item.execution_status,
                    notes=item.notes.strip(),
                    tags=item.tags,
                    transport_to_next=item.transport_to_next,
                    travel_minutes_to_next=item.travel_minutes_to_next,
                    travel_cost_cents_to_next=item.travel_cost_cents_to_next,
                )
                for item in value.items
                if item.title.strip()
            )
            if len(items) > 40:
                raise ItineraryInvalidInputError("单日活动不能超过 40 项。")
            days.append(
                ItineraryDay(
                    id=value.id or new_uuid7(),
                    local_date=value.local_date,
                    city=value.city.strip() or "待定城市",
                    summary=value.summary.strip(),
                    items=items,
                )
            )
        return tuple(days)

    @staticmethod
    def _csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
            raise ItineraryPermissionDeniedError
