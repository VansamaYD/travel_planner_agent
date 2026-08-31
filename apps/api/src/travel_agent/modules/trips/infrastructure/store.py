from __future__ import annotations

import json
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, Self, cast

from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.trips.domain.models import (
    TripDraft,
    TripInputMode,
    TripListItem,
    TripParticipant,
    TripRequirements,
    TripStatus,
    TripVersion,
    TripVisibility,
)
from travel_agent.modules.trips.infrastructure.models import (
    OutboxEventRow,
    TripParticipantRow,
    TripRequirementRow,
    TripRow,
    TripVersionRow,
)
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, value: str, *, context: str) -> bytes: ...
    def decrypt(self, payload: bytes, *, context: str) -> str: ...
    def digest(self, value: str, *, context: str) -> str: ...


class SqlAlchemyTripStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        protector: TextProtector,
    ) -> None:
        self._session_factory = session_factory
        self._protector = protector
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Trip store is not active")
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

    async def participant_snapshots(
        self, family_id: str, membership_ids: tuple[str, ...]
    ) -> tuple[dict[str, object], ...]:
        if not membership_ids:
            return ()
        unique_ids = tuple(dict.fromkeys(membership_ids))
        placeholders = ",".join(f":id_{index}" for index in range(len(unique_ids)))
        params = {f"id_{index}": value for index, value in enumerate(unique_ids)}
        params["family_id"] = family_id
        result = await self.session.execute(
            text(
                "SELECT fm.id, u.display_name_ciphertext, tp.profile_ciphertext "
                "FROM family_memberships fm JOIN users u ON u.id=fm.user_id "
                "LEFT JOIN traveler_profiles tp ON tp.membership_id=fm.id "
                "WHERE fm.family_id=:family_id AND fm.status='active' "
                f"AND fm.id IN ({placeholders})"
            ),
            params,
        )
        by_id: dict[str, dict[str, object]] = {}
        for membership_id, display_ciphertext, profile_ciphertext in result:
            profile = (
                json.loads(self._protector.decrypt(profile_ciphertext, context="traveler.profile"))
                if profile_ciphertext
                else {}
            )
            by_id[membership_id] = {
                "membership_id": membership_id,
                "display_name": self._protector.decrypt(
                    display_ciphertext, context="user.display_name"
                ),
                "member_type": profile.get("member_type", "adult"),
                "birth_year": profile.get("birth_year"),
                "discount_eligibilities": tuple(profile.get("discount_eligibilities", ())),
                "dietary_restrictions": tuple(profile.get("dietary_restrictions", ())),
                "allergies": tuple(profile.get("allergies", ())),
                "health_notes": profile.get("health_notes", ""),
                "mobility_notes": profile.get("mobility_notes", ""),
                "travel_preferences": tuple(profile.get("travel_preferences", ())),
            }
        return tuple(by_id[value] for value in unique_ids if value in by_id)

    async def create(self, draft: TripDraft, actor_user_id: str, request_id: str | None) -> None:
        self.session.add(
            TripRow(
                id=draft.id,
                family_id=draft.family_id,
                owner_user_id=draft.owner_user_id,
                title_ciphertext=self._protector.encrypt(draft.title, context="trip.title"),
                status=draft.status.value,
                visibility=draft.visibility.value,
                current_version_no=draft.version,
                start_date=draft.requirements.start_date,
                end_date=draft.requirements.end_date,
                primary_timezone="Asia/Shanghai",
                deleted_at=None,
                created_at=draft.created_at,
                updated_at=draft.updated_at,
            )
        )
        await self.session.flush()
        self._replace_projections(draft)
        self._add_version(draft, "initial", "创建旅行草稿", actor_user_id, None)
        await self._record_events(draft, actor_user_id, request_id, "trip.created")

    async def list_visible(self, user_id: str, family_id: str | None) -> tuple[TripListItem, ...]:
        statement = (
            select(TripRow, TripVersionRow)
            .join(
                TripVersionRow,
                (TripVersionRow.trip_id == TripRow.id)
                & (TripVersionRow.version_no == TripRow.current_version_no),
            )
            .where(TripRow.deleted_at.is_(None))
            .order_by(TripRow.updated_at.desc())
        )
        if family_id:
            statement = statement.where(TripRow.family_id == family_id)
        records = await self.session.execute(statement)
        items: list[TripListItem] = []
        for trip_row, version_row in records:
            if trip_row.owner_user_id != user_id:
                if trip_row.visibility == "private":
                    continue
                if await self.actor_role(trip_row.family_id, user_id) is None:
                    continue
            draft = self._decode_snapshot(version_row.snapshot_ciphertext)
            items.append(self._list_item(draft, trip_row.updated_at))
        return tuple(items)

    async def list_deleted(self, user_id: str, family_id: str | None) -> tuple[TripListItem, ...]:
        statement = (
            select(TripRow, TripVersionRow)
            .join(
                TripVersionRow,
                (TripVersionRow.trip_id == TripRow.id)
                & (TripVersionRow.version_no == TripRow.current_version_no),
            )
            .where(TripRow.deleted_at.is_not(None))
            .order_by(TripRow.deleted_at.desc())
        )
        if family_id:
            statement = statement.where(TripRow.family_id == family_id)
        records = await self.session.execute(statement)
        items: list[TripListItem] = []
        for trip_row, version_row in records:
            role = await self.actor_role(trip_row.family_id, user_id)
            if trip_row.owner_user_id != user_id and role not in {"owner", "admin"}:
                continue
            draft = self._decode_snapshot(version_row.snapshot_ciphertext)
            items.append(self._list_item(draft, trip_row.updated_at))
        return tuple(items)

    async def get(self, trip_id: str) -> TripDraft | None:
        statement = (
            select(TripVersionRow.snapshot_ciphertext)
            .join(TripRow, TripRow.id == TripVersionRow.trip_id)
            .where(
                TripRow.id == trip_id,
                TripRow.deleted_at.is_(None),
                TripVersionRow.version_no == TripRow.current_version_no,
            )
        )
        payload = await self.session.scalar(statement)
        return self._decode_snapshot(payload) if payload is not None else None

    async def get_including_deleted(self, trip_id: str) -> tuple[TripDraft, bool] | None:
        statement = (
            select(TripVersionRow.snapshot_ciphertext, TripRow.deleted_at)
            .join(TripRow, TripRow.id == TripVersionRow.trip_id)
            .where(
                TripRow.id == trip_id,
                TripVersionRow.version_no == TripRow.current_version_no,
            )
        )
        record = (await self.session.execute(statement)).one_or_none()
        if record is None:
            return None
        payload, deleted_at = record
        return self._decode_snapshot(payload), deleted_at is not None

    async def update(
        self,
        draft: TripDraft,
        expected_version: int,
        change_type: str,
        summary: str,
        actor_user_id: str,
        request_id: str | None,
    ) -> bool:
        result = cast(
            CursorResult[object],
            await self.session.execute(
                update(TripRow)
                .where(
                    TripRow.id == draft.id,
                    TripRow.current_version_no == expected_version,
                    TripRow.deleted_at.is_(None),
                )
                .values(
                    title_ciphertext=self._protector.encrypt(draft.title, context="trip.title"),
                    visibility=draft.visibility.value,
                    current_version_no=draft.version,
                    start_date=draft.requirements.start_date,
                    end_date=draft.requirements.end_date,
                    updated_at=draft.updated_at,
                )
            ),
        )
        if result.rowcount != 1:
            return False
        parent_id = await self.session.scalar(
            select(TripVersionRow.id).where(
                TripVersionRow.trip_id == draft.id,
                TripVersionRow.version_no == expected_version,
            )
        )
        await self.session.execute(
            delete(TripParticipantRow).where(TripParticipantRow.trip_id == draft.id)
        )
        await self.session.execute(
            delete(TripRequirementRow).where(TripRequirementRow.trip_id == draft.id)
        )
        self._replace_projections(draft)
        self._add_version(draft, change_type, summary, actor_user_id, parent_id)
        await self._record_events(draft, actor_user_id, request_id, "trip.updated")
        return True

    async def list_versions(self, trip_id: str) -> tuple[TripVersion, ...]:
        rows = await self.session.scalars(
            select(TripVersionRow)
            .where(TripVersionRow.trip_id == trip_id)
            .order_by(TripVersionRow.version_no.desc())
        )
        return tuple(self._version(row, include_snapshot=False) for row in rows)

    async def get_version(self, trip_id: str, version_no: int) -> TripVersion | None:
        row = await self.session.scalar(
            select(TripVersionRow).where(
                TripVersionRow.trip_id == trip_id, TripVersionRow.version_no == version_no
            )
        )
        return self._version(row, include_snapshot=True) if row else None

    async def set_deleted(
        self,
        trip_id: str,
        *,
        deleted: bool,
        actor_user_id: str,
        request_id: str | None,
        changed_at: datetime,
    ) -> bool:
        expected_state = (
            TripRow.deleted_at.is_(None) if deleted else TripRow.deleted_at.is_not(None)
        )
        result = cast(
            CursorResult[object],
            await self.session.execute(
                update(TripRow)
                .where(TripRow.id == trip_id, expected_state)
                .values(deleted_at=changed_at if deleted else None, updated_at=changed_at)
            ),
        )
        if result.rowcount != 1:
            return False
        await self._record_lifecycle_event(
            trip_id,
            "trip.deleted" if deleted else "trip.restored",
            actor_user_id,
            request_id,
            changed_at,
        )
        return True

    def _replace_projections(self, draft: TripDraft) -> None:
        requirements_json = json.dumps(
            self._requirements_dict(draft.requirements), ensure_ascii=False, separators=(",", ":")
        )
        self.session.add(
            TripRequirementRow(
                trip_id=draft.id,
                requirement_ciphertext=self._protector.encrypt(
                    requirements_json, context="trip.requirements"
                ),
                updated_at=draft.updated_at,
            )
        )
        for participant in draft.participants:
            payload = json.dumps(
                self._participant_dict(participant), ensure_ascii=False, separators=(",", ":")
            )
            self.session.add(
                TripParticipantRow(
                    id=participant.id,
                    trip_id=draft.id,
                    source_membership_id=participant.source_membership_id,
                    snapshot_ciphertext=self._protector.encrypt(
                        payload, context="trip.participant"
                    ),
                    is_temporary=participant.is_temporary,
                    created_at=draft.updated_at,
                )
            )

    def _add_version(
        self,
        draft: TripDraft,
        change_type: str,
        summary: str,
        actor_user_id: str,
        parent_id: str | None,
    ) -> None:
        canonical = json.dumps(
            self._draft_dict(draft), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.session.add(
            TripVersionRow(
                id=new_uuid7(),
                trip_id=draft.id,
                version_no=draft.version,
                parent_version_id=parent_id,
                change_type=change_type,
                snapshot_ciphertext=self._protector.encrypt(
                    canonical, context="trip.version.snapshot"
                ),
                snapshot_hash=self._protector.digest(canonical, context="trip.version.digest"),
                summary_ciphertext=self._protector.encrypt(summary, context="trip.version.summary"),
                created_by_user_id=actor_user_id,
                created_at=draft.updated_at,
            )
        )

    async def _record_events(
        self,
        draft: TripDraft,
        actor_user_id: str,
        request_id: str | None,
        event_type: str,
    ) -> None:
        await self.session.execute(
            text(
                "INSERT INTO audit_events "
                "(id,event_type,actor_user_id,source_type,subject_type,subject_id,"
                "request_id,details_json,created_at) VALUES "
                "(:id,:event_type,:actor,'user','trip',:trip_id,:request_id,:details,:created_at)"
            ),
            {
                "id": new_uuid7(),
                "event_type": event_type,
                "actor": actor_user_id,
                "trip_id": draft.id,
                "request_id": request_id,
                "details": json.dumps({"version": draft.version, "family_id": draft.family_id}),
                "created_at": draft.updated_at,
            },
        )
        self.session.add(
            OutboxEventRow(
                id=new_uuid7(),
                event_type=event_type,
                aggregate_type="trip",
                aggregate_id=draft.id,
                payload_json={"trip_id": draft.id, "version": draft.version},
                status="pending",
                available_at=draft.updated_at,
                created_at=draft.updated_at,
                processed_at=None,
            )
        )

    def _decode_snapshot(self, payload: bytes) -> TripDraft:
        value = json.loads(self._protector.decrypt(payload, context="trip.version.snapshot"))
        requirements = value["requirements"]
        return TripDraft(
            id=value["id"],
            family_id=value["family_id"],
            owner_user_id=value["owner_user_id"],
            title=value["title"],
            status=TripStatus(value["status"]),
            visibility=TripVisibility(value["visibility"]),
            version=value["version"],
            requirements=TripRequirements(
                input_mode=TripInputMode(requirements["input_mode"]),
                origin=requirements["origin"],
                destinations=tuple(requirements["destinations"]),
                start_date=date.fromisoformat(requirements["start_date"])
                if requirements["start_date"]
                else None,
                end_date=date.fromisoformat(requirements["end_date"])
                if requirements["end_date"]
                else None,
                budget_cents=requirements["budget_cents"],
                currency=requirements["currency"],
                styles=tuple(requirements["styles"]),
                pace=requirements["pace"],
                transportation=tuple(requirements["transportation"]),
                hard_constraints=tuple(requirements["hard_constraints"]),
                soft_preferences=tuple(requirements["soft_preferences"]),
                assumptions=tuple(requirements["assumptions"]),
                source_text=requirements["source_text"],
                confirmed=requirements["confirmed"],
            ),
            participants=tuple(
                TripParticipant(
                    **{
                        **p,
                        "discount_eligibilities": tuple(p["discount_eligibilities"]),
                        "dietary_restrictions": tuple(p["dietary_restrictions"]),
                        "allergies": tuple(p["allergies"]),
                        "travel_preferences": tuple(p["travel_preferences"]),
                    }
                )
                for p in value["participants"]
            ),
            warnings=tuple(value["warnings"]),
            created_at=datetime.fromisoformat(value["created_at"]),
            updated_at=datetime.fromisoformat(value["updated_at"]),
        )

    def _version(self, row: TripVersionRow, *, include_snapshot: bool) -> TripVersion:
        return TripVersion(
            id=row.id,
            trip_id=row.trip_id,
            version_no=row.version_no,
            change_type=row.change_type,
            summary=self._protector.decrypt(row.summary_ciphertext, context="trip.version.summary"),
            created_by_user_id=row.created_by_user_id,
            created_at=row.created_at,
            snapshot=self._decode_snapshot(row.snapshot_ciphertext) if include_snapshot else None,
        )

    @staticmethod
    def _list_item(draft: TripDraft, updated_at: datetime) -> TripListItem:
        return TripListItem(
            id=draft.id,
            family_id=draft.family_id,
            owner_user_id=draft.owner_user_id,
            title=draft.title,
            status=draft.status,
            visibility=draft.visibility,
            version=draft.version,
            origin=draft.requirements.origin,
            destinations=draft.requirements.destinations,
            start_date=draft.requirements.start_date,
            end_date=draft.requirements.end_date,
            participant_count=len(draft.participants),
            updated_at=updated_at,
        )

    async def _record_lifecycle_event(
        self,
        trip_id: str,
        event_type: str,
        actor_user_id: str,
        request_id: str | None,
        changed_at: datetime,
    ) -> None:
        await self.session.execute(
            text(
                "INSERT INTO audit_events "
                "(id,event_type,actor_user_id,source_type,subject_type,subject_id,"
                "request_id,details_json,created_at) VALUES "
                "(:id,:event_type,:actor,'user','trip',:trip_id,:request_id,:details,:created_at)"
            ),
            {
                "id": new_uuid7(),
                "event_type": event_type,
                "actor": actor_user_id,
                "trip_id": trip_id,
                "request_id": request_id,
                "details": json.dumps({"lifecycle": event_type}),
                "created_at": changed_at,
            },
        )
        self.session.add(
            OutboxEventRow(
                id=new_uuid7(),
                event_type=event_type,
                aggregate_type="trip",
                aggregate_id=trip_id,
                payload_json={"trip_id": trip_id},
                status="pending",
                available_at=changed_at,
                created_at=changed_at,
                processed_at=None,
            )
        )

    @classmethod
    def _draft_dict(cls, draft: TripDraft) -> dict[str, object]:
        return {
            "id": draft.id,
            "family_id": draft.family_id,
            "owner_user_id": draft.owner_user_id,
            "title": draft.title,
            "status": draft.status.value,
            "visibility": draft.visibility.value,
            "version": draft.version,
            "requirements": cls._requirements_dict(draft.requirements),
            "participants": [cls._participant_dict(item) for item in draft.participants],
            "warnings": list(draft.warnings),
            "created_at": draft.created_at.isoformat(),
            "updated_at": draft.updated_at.isoformat(),
        }

    @staticmethod
    def _requirements_dict(value: TripRequirements) -> dict[str, object]:
        return {
            "input_mode": value.input_mode.value,
            "origin": value.origin,
            "destinations": list(value.destinations),
            "start_date": value.start_date.isoformat() if value.start_date else None,
            "end_date": value.end_date.isoformat() if value.end_date else None,
            "budget_cents": value.budget_cents,
            "currency": value.currency,
            "styles": list(value.styles),
            "pace": value.pace,
            "transportation": list(value.transportation),
            "hard_constraints": list(value.hard_constraints),
            "soft_preferences": list(value.soft_preferences),
            "assumptions": list(value.assumptions),
            "source_text": value.source_text,
            "confirmed": value.confirmed,
        }

    @staticmethod
    def _participant_dict(value: TripParticipant) -> dict[str, object]:
        return {
            "id": value.id,
            "source_membership_id": value.source_membership_id,
            "display_name": value.display_name,
            "member_type": value.member_type,
            "birth_year": value.birth_year,
            "discount_eligibilities": list(value.discount_eligibilities),
            "dietary_restrictions": list(value.dietary_restrictions),
            "allergies": list(value.allergies),
            "health_notes": value.health_notes,
            "mobility_notes": value.mobility_notes,
            "travel_preferences": list(value.travel_preferences),
            "is_temporary": value.is_temporary,
        }
