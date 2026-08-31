from __future__ import annotations

import json
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, Self, cast

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.itinerary.domain.models import (
    ItineraryDay,
    ItineraryItem,
    ItineraryPlan,
    ItineraryVersionSummary,
)
from travel_agent.modules.itinerary.infrastructure.models import (
    ItineraryDayRow,
    ItineraryItemRow,
    ItineraryLegRow,
    ItineraryVersionRow,
)
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, value: str, *, context: str) -> bytes: ...
    def decrypt(self, payload: bytes, *, context: str) -> str: ...
    def digest(self, value: str, *, context: str) -> str: ...


class SqlAlchemyItineraryStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], protector: TextProtector
    ) -> None:
        self._session_factory = session_factory
        self._protector = protector
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Itinerary store is not active")
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

    async def actor_role(self, family_id: str, user_id: str) -> str | None:
        result = await self.session.execute(
            text(
                "SELECT role FROM family_memberships "
                "WHERE family_id=:family_id AND user_id=:user_id AND status='active'"
            ),
            {"family_id": family_id, "user_id": user_id},
        )
        return cast(str | None, result.scalar_one_or_none())

    async def trip_context(self, trip_id: str) -> dict[str, object] | None:
        result = await self.session.execute(
            text(
                "SELECT t.family_id,t.owner_user_id,t.visibility,t.start_date,t.end_date,"
                "v.snapshot_ciphertext FROM trips t JOIN trip_versions v "
                "ON v.trip_id=t.id AND v.version_no=t.current_version_no "
                "WHERE t.id=:trip_id AND t.deleted_at IS NULL"
            ),
            {"trip_id": trip_id},
        )
        record = result.one_or_none()
        if record is None:
            return None
        family_id, owner_user_id, visibility, start_date, end_date, snapshot = record
        trip_snapshot = json.loads(
            self._protector.decrypt(snapshot, context="trip.version.snapshot")
        )
        return {
            "family_id": family_id,
            "owner_user_id": owner_user_id,
            "visibility": visibility,
            "start_date": date.fromisoformat(start_date)
            if isinstance(start_date, str)
            else start_date,
            "end_date": date.fromisoformat(end_date) if isinstance(end_date, str) else end_date,
            "destinations": trip_snapshot["requirements"]["destinations"],
        }

    async def current(self, trip_id: str) -> ItineraryPlan | None:
        payload = await self.session.scalar(
            text(
                "SELECT v.snapshot_ciphertext FROM trips t JOIN itinerary_versions v "
                "ON v.id=t.current_itinerary_version_id "
                "WHERE t.id=:trip_id AND t.deleted_at IS NULL"
            ),
            {"trip_id": trip_id},
        )
        return self._decode(payload) if payload is not None else None

    async def create(self, plan: ItineraryPlan, summary: str, request_id: str | None) -> None:
        row = self._version_row(plan, None, "initial", summary)
        self.session.add(row)
        await self.session.flush()
        await self.session.execute(
            text(
                "UPDATE trips SET current_itinerary_version_id=:version_id,"
                "updated_at=:updated_at WHERE id=:trip_id"
            ),
            {"version_id": row.id, "updated_at": plan.created_at, "trip_id": plan.trip_id},
        )
        await self._add_projections(plan, row.id)
        await self._events(plan, "itinerary.created", request_id)

    async def update(
        self, plan: ItineraryPlan, expected_version: int, summary: str, request_id: str | None
    ) -> bool:
        parent = await self.session.scalar(
            select(ItineraryVersionRow).where(
                ItineraryVersionRow.trip_id == plan.trip_id,
                ItineraryVersionRow.version_no == expected_version,
            )
        )
        if parent is None:
            return False
        current_version_id = await self.session.scalar(
            text("SELECT current_itinerary_version_id FROM trips WHERE id=:trip_id"),
            {"trip_id": plan.trip_id},
        )
        if current_version_id != parent.id:
            return False
        row = self._version_row(plan, parent.id, "user_edit", summary)
        self.session.add(row)
        await self.session.flush()
        result = cast(
            CursorResult[object],
            await self.session.execute(
                text(
                    "UPDATE trips SET current_itinerary_version_id=:next_id,updated_at=:updated_at "
                    "WHERE id=:trip_id AND current_itinerary_version_id=:parent_id "
                    "AND deleted_at IS NULL"
                ),
                {
                    "next_id": row.id,
                    "updated_at": plan.created_at,
                    "trip_id": plan.trip_id,
                    "parent_id": parent.id,
                },
            ),
        )
        if result.rowcount != 1:
            return False
        await self._add_projections(plan, row.id)
        await self._events(plan, "itinerary.updated", request_id)
        return True

    async def versions(self, trip_id: str) -> tuple[ItineraryVersionSummary, ...]:
        rows = await self.session.scalars(
            select(ItineraryVersionRow)
            .where(ItineraryVersionRow.trip_id == trip_id)
            .order_by(ItineraryVersionRow.version_no.desc())
        )
        return tuple(
            ItineraryVersionSummary(
                id=row.id,
                trip_id=row.trip_id,
                version=row.version_no,
                change_type=row.change_type,
                summary=self._protector.decrypt(
                    row.summary_ciphertext, context="itinerary.version.summary"
                ),
                created_by_user_id=row.created_by_user_id,
                created_at=row.created_at,
            )
            for row in rows
        )

    def _version_row(
        self, plan: ItineraryPlan, parent_id: str | None, change_type: str, summary: str
    ) -> ItineraryVersionRow:
        canonical = json.dumps(
            self._plan_dict(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return ItineraryVersionRow(
            id=plan.id,
            trip_id=plan.trip_id,
            version_no=plan.version,
            parent_version_id=parent_id,
            change_type=change_type,
            snapshot_schema_version=1,
            snapshot_ciphertext=self._protector.encrypt(
                canonical, context="itinerary.version.snapshot"
            ),
            snapshot_hash=self._protector.digest(canonical, context="itinerary.version.digest"),
            summary_ciphertext=self._protector.encrypt(
                summary, context="itinerary.version.summary"
            ),
            created_by_user_id=plan.created_by_user_id,
            created_at=plan.created_at,
        )

    async def _add_projections(self, plan: ItineraryPlan, version_id: str) -> None:
        for day_index, day in enumerate(plan.days):
            day_row = ItineraryDayRow(
                id=new_uuid7(),
                itinerary_version_id=version_id,
                local_date=day.local_date,
                city_ciphertext=self._protector.encrypt(day.city, context="itinerary.day.city"),
                summary_ciphertext=self._protector.encrypt(
                    day.summary, context="itinerary.day.summary"
                ),
                sort_order=day_index,
            )
            self.session.add(day_row)
            await self.session.flush()
            for item_index, item in enumerate(day.items):
                self.session.add(
                    ItineraryItemRow(
                        id=new_uuid7(),
                        itinerary_version_id=version_id,
                        itinerary_day_id=day_row.id,
                        logical_id=item.logical_id,
                        item_type=item.item_type,
                        title_ciphertext=self._protector.encrypt(
                            item.title, context="itinerary.item.title"
                        ),
                        place_name_ciphertext=self._protector.encrypt(
                            item.place_name, context="itinerary.item.place"
                        ),
                        start_time=item.start_time,
                        end_time=item.end_time,
                        cost_cents=item.cost_cents,
                        execution_status=item.execution_status,
                        notes_ciphertext=self._protector.encrypt(
                            item.notes, context="itinerary.item.notes"
                        ),
                        tags_json=list(item.tags),
                        transport_to_next=item.transport_to_next,
                        travel_minutes_to_next=item.travel_minutes_to_next,
                        travel_cost_cents_to_next=item.travel_cost_cents_to_next,
                        sort_order=item_index,
                    )
                )
                if item.transport_to_next and item_index + 1 < len(day.items):
                    self.session.add(
                        ItineraryLegRow(
                            id=new_uuid7(),
                            itinerary_version_id=version_id,
                            from_item_logical_id=item.logical_id,
                            to_item_logical_id=day.items[item_index + 1].logical_id,
                            mode=item.transport_to_next,
                            duration_minutes=item.travel_minutes_to_next,
                            cost_cents=item.travel_cost_cents_to_next,
                            source_json={"source": "user"},
                        )
                    )

    async def _events(self, plan: ItineraryPlan, event_type: str, request_id: str | None) -> None:
        await self.session.execute(
            text(
                "INSERT INTO audit_events "
                "(id,event_type,actor_user_id,source_type,subject_type,subject_id,"
                "request_id,details_json,created_at) VALUES "
                "(:id,:event_type,:actor,'user','itinerary',:trip_id,"
                ":request_id,:details,:created_at)"
            ),
            {
                "id": new_uuid7(),
                "event_type": event_type,
                "actor": plan.created_by_user_id,
                "trip_id": plan.trip_id,
                "request_id": request_id,
                "details": json.dumps({"version": plan.version}),
                "created_at": plan.created_at,
            },
        )
        await self.session.execute(
            text(
                "INSERT INTO outbox_events "
                "(id,event_type,aggregate_type,aggregate_id,payload_json,status,"
                "available_at,created_at,processed_at) VALUES "
                "(:id,:event_type,'itinerary',:trip_id,:payload,'pending',"
                ":created_at,:created_at,NULL)"
            ),
            {
                "id": new_uuid7(),
                "event_type": event_type,
                "trip_id": plan.trip_id,
                "payload": json.dumps({"trip_id": plan.trip_id, "version": plan.version}),
                "created_at": plan.created_at,
            },
        )

    def _decode(self, payload: bytes) -> ItineraryPlan:
        value = json.loads(self._protector.decrypt(payload, context="itinerary.version.snapshot"))
        return ItineraryPlan(
            id=value["id"],
            trip_id=value["trip_id"],
            version=value["version"],
            days=tuple(
                ItineraryDay(
                    id=day["id"],
                    local_date=date.fromisoformat(day["local_date"]),
                    city=day["city"],
                    summary=day["summary"],
                    items=tuple(
                        ItineraryItem(**{**item, "tags": tuple(item["tags"])})
                        for item in day["items"]
                    ),
                )
                for day in value["days"]
            ),
            currency=value["currency"],
            estimated_total_cost_cents=value["estimated_total_cost_cents"],
            warnings=tuple(value["warnings"]),
            created_by_user_id=value["created_by_user_id"],
            created_at=datetime.fromisoformat(value["created_at"]),
        )

    @staticmethod
    def _plan_dict(plan: ItineraryPlan) -> dict[str, object]:
        return {
            "id": plan.id,
            "trip_id": plan.trip_id,
            "version": plan.version,
            "days": [
                {
                    "id": day.id,
                    "local_date": day.local_date.isoformat(),
                    "city": day.city,
                    "summary": day.summary,
                    "items": [
                        {
                            "logical_id": item.logical_id,
                            "item_type": item.item_type,
                            "title": item.title,
                            "place_name": item.place_name,
                            "start_time": item.start_time,
                            "end_time": item.end_time,
                            "cost_cents": item.cost_cents,
                            "execution_status": item.execution_status,
                            "notes": item.notes,
                            "tags": list(item.tags),
                            "transport_to_next": item.transport_to_next,
                            "travel_minutes_to_next": item.travel_minutes_to_next,
                            "travel_cost_cents_to_next": item.travel_cost_cents_to_next,
                        }
                        for item in day.items
                    ],
                }
                for day in plan.days
            ],
            "currency": plan.currency,
            "estimated_total_cost_cents": plan.estimated_total_cost_cents,
            "warnings": list(plan.warnings),
            "created_by_user_id": plan.created_by_user_id,
            "created_at": plan.created_at.isoformat(),
        }
