from __future__ import annotations

import json
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self, cast
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.knowledge.domain import ImageAnalysis, PlaceCard
from travel_agent.modules.knowledge.models import (
    ImageAnalysisRow,
    PlaceKnowledgeCardRow,
    PlaceKnowledgeRevisionRow,
)
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, value: str, *, context: str) -> bytes: ...
    def decrypt(self, payload: bytes, *, context: str) -> str: ...
    def digest(self, value: str, *, context: str) -> str: ...


class SqlAlchemyKnowledgeStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], protector: TextProtector
    ) -> None:
        self._factory, self._protector = session_factory, protector
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc_type:
                await self._session.rollback()
            await self._session.close()
        self._session = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Knowledge store inactive")
        return self._session

    async def commit(self) -> None:
        await self.session.commit()

    def identity_hash(self, owner_user_id: str, provider_id: str, name: str, city: str) -> str:
        canonical = provider_id or f"{name.strip().casefold()}|{city.strip().casefold()}"
        return self._protector.digest(canonical, context=f"place.identity.{owner_user_id}")

    async def upsert_place(
        self,
        owner_user_id: str,
        *,
        provider_id: str,
        entity_type: str,
        name: str,
        city: str,
        address: str,
        intro: str,
        details: dict[str, object],
        longitude: float | None,
        latitude: float | None,
        confidence: float,
        verified_at: datetime,
        expires_at: datetime | None,
        reason: str,
    ) -> PlaceCard:
        identity = self.identity_hash(owner_user_id, provider_id, name, city)
        row = await self.session.scalar(
            select(PlaceKnowledgeCardRow).where(
                PlaceKnowledgeCardRow.owner_user_id == owner_user_id,
                PlaceKnowledgeCardRow.identity_hash == identity,
            )
        )
        if row is None:
            candidates = await self.session.scalars(
                select(PlaceKnowledgeCardRow).where(
                    PlaceKnowledgeCardRow.owner_user_id == owner_user_id
                )
            )
            row = next(
                (
                    candidate
                    for candidate in candidates
                    if self._decrypt(candidate.name_ciphertext, "place.name").casefold()
                    == name.strip().casefold()
                    and self._decrypt(candidate.city_ciphertext, "place.city").casefold()
                    == city.strip().casefold()
                ),
                None,
            )
        revision_required = row is None
        if row is None:
            row = PlaceKnowledgeCardRow(
                id=new_uuid7(),
                owner_user_id=owner_user_id,
                identity_hash=identity,
                entity_type=entity_type,
                name_ciphertext=self._encrypt(name, "place.name"),
                city_ciphertext=self._optional(city, "place.city"),
                address_ciphertext=self._optional(address, "place.address"),
                intro_ciphertext=self._optional(intro, "place.intro"),
                details_ciphertext=self._json(details, "place.details"),
                longitude=longitude,
                latitude=latitude,
                confidence=confidence,
                version=1,
                last_verified_at=verified_at,
                expires_at=expires_at,
                created_at=verified_at,
                updated_at=verified_at,
            )
            self.session.add(row)
        else:
            current = self._card(row)
            old_details = self._decode_json(row.details_ciphertext, "place.details")
            merged_details = {**old_details, **details}
            revision_required = any(
                (
                    entity_type and entity_type != current.entity_type,
                    name != current.name,
                    city != current.city,
                    address != current.address,
                    bool(intro and intro != current.intro),
                    longitude is not None and longitude != current.longitude,
                    latitude is not None and latitude != current.latitude,
                    _semantic_details(merged_details) != _semantic_details(current.details),
                )
            )
            row.entity_type = entity_type or row.entity_type
            row.name_ciphertext = self._encrypt(name, "place.name")
            row.city_ciphertext = self._optional(city, "place.city")
            row.address_ciphertext = self._optional(address, "place.address")
            if intro:
                row.intro_ciphertext = self._encrypt(intro, "place.intro")
            row.details_ciphertext = self._json(merged_details, "place.details")
            row.longitude = longitude if longitude is not None else row.longitude
            row.latitude = latitude if latitude is not None else row.latitude
            row.confidence = max(row.confidence, confidence)
            if revision_required:
                row.version += 1
            row.last_verified_at = verified_at
            row.expires_at = expires_at
            row.updated_at = verified_at
        await self.session.flush()
        if revision_required:
            await self._revision(row, reason, verified_at)
        return self._card(row)

    async def list_places(self, owner_user_id: str, limit: int = 100) -> tuple[PlaceCard, ...]:
        rows = await self.session.scalars(
            select(PlaceKnowledgeCardRow)
            .where(PlaceKnowledgeCardRow.owner_user_id == owner_user_id)
            .order_by(PlaceKnowledgeCardRow.updated_at.desc())
            .limit(limit)
        )
        return tuple(self._card(row) for row in rows)

    async def get_place(self, owner_user_id: str, card_id: str) -> PlaceCard | None:
        row = await self.session.scalar(
            select(PlaceKnowledgeCardRow).where(
                PlaceKnowledgeCardRow.id == card_id,
                PlaceKnowledgeCardRow.owner_user_id == owner_user_id,
            )
        )
        return self._card(row) if row else None

    async def update_place(
        self,
        owner_user_id: str,
        card_id: str,
        changes: dict[str, object],
        updated_at: datetime,
    ) -> PlaceCard | None:
        row = await self.session.scalar(
            select(PlaceKnowledgeCardRow).where(
                PlaceKnowledgeCardRow.id == card_id,
                PlaceKnowledgeCardRow.owner_user_id == owner_user_id,
            )
        )
        if row is None:
            return None
        for field, context in (
            ("name", "place.name"),
            ("city", "place.city"),
            ("address", "place.address"),
            ("intro", "place.intro"),
        ):
            if field in changes:
                setattr(row, f"{field}_ciphertext", self._optional(str(changes[field]), context))
        if "entity_type" in changes:
            row.entity_type = str(changes["entity_type"])
        if isinstance(changes.get("details"), dict):
            current = self._decode_json(row.details_ciphertext, "place.details")
            details = cast(dict[str, object], changes["details"])
            row.details_ciphertext = self._json({**current, **details}, "place.details")
        row.version += 1
        row.updated_at = updated_at
        await self.session.flush()
        await self._revision(row, "user_edit", updated_at)
        return self._card(row)

    async def find_place(self, owner_user_id: str, name: str, city: str) -> PlaceCard | None:
        for value in await self.list_places(owner_user_id):
            if value.name.strip().casefold() == name.strip().casefold() and (
                not city or value.city.strip().casefold() == city.strip().casefold()
            ):
                return value
        return None

    async def find_image_analysis(
        self, owner_user_id: str, identity_hash: str, model_name: str, prompt_version: str
    ) -> ImageAnalysis | None:
        row = await self.session.scalar(
            select(ImageAnalysisRow).where(
                ImageAnalysisRow.owner_user_id == owner_user_id,
                ImageAnalysisRow.image_identity_hash == identity_hash,
                ImageAnalysisRow.model_name == model_name,
                ImageAnalysisRow.prompt_version == prompt_version,
            )
        )
        return self._analysis(row) if row and row.status == "completed" else None

    async def start_image_analysis(
        self,
        owner_user_id: str,
        identity_hash: str,
        source_url: str,
        model_name: str,
        prompt_version: str,
        mode: str,
        created_at: datetime,
    ) -> str:
        row = await self.session.scalar(
            select(ImageAnalysisRow).where(
                ImageAnalysisRow.owner_user_id == owner_user_id,
                ImageAnalysisRow.image_identity_hash == identity_hash,
                ImageAnalysisRow.model_name == model_name,
                ImageAnalysisRow.prompt_version == prompt_version,
            )
        )
        if row is None:
            row = ImageAnalysisRow(
                id=new_uuid7(),
                owner_user_id=owner_user_id,
                image_identity_hash=identity_hash,
                source_url_ciphertext=self._encrypt(source_url, "image.source_url"),
                model_name=model_name,
                prompt_version=prompt_version,
                analysis_mode=mode,
                status="processing",
                result_ciphertext=None,
                error_ciphertext=None,
                created_at=created_at,
                analyzed_at=None,
            )
            self.session.add(row)
        else:
            row.status = "processing"
            row.error_ciphertext = None
        await self.session.flush()
        return row.id

    async def finish_image_analysis(
        self, record_id: str, result: dict[str, object], analyzed_at: datetime
    ) -> ImageAnalysis:
        row = await self.session.get(ImageAnalysisRow, record_id)
        if row is None:
            raise RuntimeError("Image analysis record missing")
        row.status = "completed"
        row.result_ciphertext = self._json(result, "image.result")
        row.analyzed_at = analyzed_at
        await self.session.flush()
        return self._analysis(row)

    async def fail_image_analysis(self, record_id: str, error: str) -> None:
        row = await self.session.get(ImageAnalysisRow, record_id)
        if row:
            row.status = "failed"
            row.error_ciphertext = self._encrypt(error[:1000], "image.error")

    def image_hash(self, owner_user_id: str, source_url: str) -> str:
        parsed = urlsplit(source_url.strip())
        normalized = urlunsplit(
            (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path, "", "")
        )
        return self._protector.digest(normalized, context=f"image.identity.{owner_user_id}")

    async def _revision(
        self, row: PlaceKnowledgeCardRow, reason: str, created_at: datetime
    ) -> None:
        snapshot = self._serialize_card(self._card(row))
        self.session.add(
            PlaceKnowledgeRevisionRow(
                id=new_uuid7(),
                card_id=row.id,
                version=row.version,
                reason=reason[:80],
                snapshot_ciphertext=self._json(snapshot, "place.revision"),
                created_at=created_at,
            )
        )

    def _card(self, row: PlaceKnowledgeCardRow) -> PlaceCard:
        return PlaceCard(
            id=row.id,
            entity_type=row.entity_type,
            name=self._decrypt(row.name_ciphertext, "place.name"),
            city=self._decrypt(row.city_ciphertext, "place.city"),
            address=self._decrypt(row.address_ciphertext, "place.address"),
            intro=self._decrypt(row.intro_ciphertext, "place.intro"),
            details=self._decode_json(row.details_ciphertext, "place.details"),
            longitude=row.longitude,
            latitude=row.latitude,
            confidence=row.confidence,
            version=row.version,
            last_verified_at=_aware(row.last_verified_at) if row.last_verified_at else None,
            expires_at=_aware(row.expires_at) if row.expires_at else None,
            updated_at=_aware(row.updated_at),
        )

    def _analysis(self, row: ImageAnalysisRow) -> ImageAnalysis:
        return ImageAnalysis(
            id=row.id,
            source_url=self._decrypt(row.source_url_ciphertext, "image.source_url"),
            model_name=row.model_name,
            prompt_version=row.prompt_version,
            analysis_mode=row.analysis_mode,
            status=row.status,
            result=self._decode_json(row.result_ciphertext, "image.result"),
            created_at=_aware(row.created_at),
            analyzed_at=_aware(row.analyzed_at) if row.analyzed_at else None,
        )

    @staticmethod
    def _serialize_card(value: PlaceCard) -> dict[str, object]:
        return {
            "id": value.id,
            "entity_type": value.entity_type,
            "name": value.name,
            "city": value.city,
            "address": value.address,
            "intro": value.intro,
            "details": value.details,
            "longitude": value.longitude,
            "latitude": value.latitude,
            "confidence": value.confidence,
            "version": value.version,
        }

    def _encrypt(self, value: str, context: str) -> bytes:
        return self._protector.encrypt(value, context=context)

    def _optional(self, value: str, context: str) -> bytes | None:
        return self._encrypt(value, context) if value else None

    def _decrypt(self, value: bytes | None, context: str) -> str:
        return self._protector.decrypt(value, context=context) if value else ""

    def _json(self, value: object, context: str) -> bytes:
        return self._encrypt(json.dumps(value, ensure_ascii=False, separators=(",", ":")), context)

    def _decode_json(self, value: bytes | None, context: str) -> dict[str, object]:
        if value is None:
            return {}
        try:
            decoded = json.loads(self._decrypt(value, context))
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _semantic_details(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    sources = result.get("sources")
    if isinstance(sources, list):
        result["sources"] = [
            {key: item for key, item in source.items() if key != "checked_at"}
            for source in sources
            if isinstance(source, dict)
        ]
    return result
