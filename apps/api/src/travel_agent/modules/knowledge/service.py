from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol

from travel_agent.modules.knowledge.domain import ImageAnalysis, PlaceCard


class Clock(Protocol):
    def now(self) -> datetime: ...


class VisionProvider(Protocol):
    model_name: str
    prompt_version: str

    async def analyze(self, source_url: str, mode: str) -> dict[str, object]: ...


class KnowledgeStore(Protocol):
    async def commit(self) -> None: ...
    def identity_hash(self, owner_user_id: str, provider_id: str, name: str, city: str) -> str: ...
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
    ) -> PlaceCard: ...
    async def list_places(self, owner_user_id: str, limit: int = 100) -> tuple[PlaceCard, ...]: ...
    async def get_place(self, owner_user_id: str, card_id: str) -> PlaceCard | None: ...
    async def update_place(
        self, owner_user_id: str, card_id: str, changes: dict[str, object], updated_at: datetime
    ) -> PlaceCard | None: ...
    async def find_place(self, owner_user_id: str, name: str, city: str) -> PlaceCard | None: ...
    def image_hash(self, owner_user_id: str, source_url: str) -> str: ...
    async def find_image_analysis(
        self, owner_user_id: str, identity_hash: str, model_name: str, prompt_version: str
    ) -> ImageAnalysis | None: ...
    async def start_image_analysis(
        self,
        owner_user_id: str,
        identity_hash: str,
        source_url: str,
        model_name: str,
        prompt_version: str,
        mode: str,
        created_at: datetime,
    ) -> str: ...
    async def finish_image_analysis(
        self, record_id: str, result: dict[str, object], analyzed_at: datetime
    ) -> ImageAnalysis: ...
    async def fail_image_analysis(self, record_id: str, error: str) -> None: ...
    async def __aenter__(self) -> KnowledgeStore: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class KnowledgeService:
    def __init__(
        self,
        store_factory: Callable[[], KnowledgeStore],
        vision: VisionProvider,
        clock: Clock,
    ) -> None:
        self._store_factory, self._vision, self._clock = store_factory, vision, clock

    async def capture_place_results(
        self, owner_user_id: str, data: dict[str, object], reason: str = "map_refresh"
    ) -> tuple[PlaceCard, ...]:
        places = data.get("places")
        if not isinstance(places, list):
            return ()
        now = self._clock.now()
        values: list[PlaceCard] = []
        async with self._store_factory() as store:
            for item in places[:10]:
                if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                    continue
                type_text = str(item.get("type") or "")
                details = {
                    "tags": [value for value in type_text.split(";") if value],
                    "rating": item.get("rating"),
                    "average_cost": item.get("average_cost"),
                    "district": item.get("district"),
                    "sources": [
                        {
                            "provider": "amap",
                            "external_id": item.get("id"),
                            "checked_at": now.isoformat(),
                        }
                    ],
                }
                values.append(
                    await store.upsert_place(
                        owner_user_id,
                        provider_id=f"amap:{item.get('id')}" if item.get("id") else "",
                        entity_type=_entity_type(type_text),
                        name=str(item.get("name") or "")[:200],
                        city=_city_name(str(item.get("city") or ""))[:100],
                        address=str(item.get("address") or "")[:500],
                        intro="",
                        details=details,
                        longitude=_float(item.get("longitude")),
                        latitude=_float(item.get("latitude")),
                        confidence=0.9,
                        verified_at=now,
                        expires_at=now + timedelta(days=30),
                        reason=reason,
                    )
                )
            await store.commit()
        return tuple(values)

    async def list_places(
        self,
        owner_user_id: str,
        query: str = "",
        city: str = "",
        entity_type: str = "",
    ) -> tuple[PlaceCard, ...]:
        async with self._store_factory() as store:
            values = await store.list_places(owner_user_id)
        query_folded, city_folded = query.strip().casefold(), _city_name(city).casefold()
        return tuple(
            value
            for value in values
            if (not query_folded or query_folded in value.name.casefold())
            and (not city_folded or city_folded == _city_name(value.city).casefold())
            and (not entity_type or entity_type == value.entity_type)
        )

    async def find_place(self, owner_user_id: str, name: str, city: str) -> PlaceCard | None:
        async with self._store_factory() as store:
            return await store.find_place(owner_user_id, name, city)

    async def update_place(
        self, owner_user_id: str, card_id: str, changes: dict[str, object]
    ) -> PlaceCard | None:
        async with self._store_factory() as store:
            value = await store.update_place(owner_user_id, card_id, changes, self._clock.now())
            await store.commit()
            return value

    async def upsert_agent_claim(self, owner_user_id: str, claim: dict[str, object]) -> PlaceCard:
        name = str(claim.get("name") or "").strip()
        city = _city_name(str(claim.get("city") or ""))
        evidence_source = str(claim.get("evidence_source") or "").strip()
        if not name or not city or not evidence_source:
            raise ValueError("地点名称、城市和证据来源不能为空。")
        raw_details = claim.get("details")
        details = dict(raw_details) if isinstance(raw_details, dict) else {}
        details["evidence"] = {
            "source": evidence_source[:2000],
            "observed_at": str(claim.get("observed_at") or self._clock.now().isoformat())[:80],
            "kind": "agent_extracted_claim",
        }
        now = self._clock.now()
        async with self._store_factory() as store:
            value = await store.upsert_place(
                owner_user_id,
                provider_id="",
                entity_type=str(claim.get("entity_type") or "other")[:24],
                name=name[:200],
                city=city[:100],
                address=str(claim.get("address") or "")[:500],
                intro=str(claim.get("intro") or "")[:8000],
                details=details,
                longitude=_float(claim.get("longitude")),
                latitude=_float(claim.get("latitude")),
                confidence=min(max(_float(claim.get("confidence")) or 0.6, 0.1), 0.75),
                verified_at=now,
                expires_at=now + timedelta(days=7),
                reason="agent_evidence_merge",
            )
            await store.commit()
            return value

    async def analyze_image(
        self, owner_user_id: str, source_url: str, mode: str = "auto"
    ) -> tuple[ImageAnalysis, bool]:
        async with self._store_factory() as store:
            identity = store.image_hash(owner_user_id, source_url)
            cached = await store.find_image_analysis(
                owner_user_id, identity, self._vision.model_name, self._vision.prompt_version
            )
            if cached:
                return cached, True
            record_id = await store.start_image_analysis(
                owner_user_id,
                identity,
                source_url,
                self._vision.model_name,
                self._vision.prompt_version,
                mode,
                self._clock.now(),
            )
            await store.commit()
        try:
            result = await self._vision.analyze(source_url, mode)
            result["identity_basis"] = "source_url"
            async with self._store_factory() as store:
                value = await store.finish_image_analysis(record_id, result, self._clock.now())
                await store.commit()
            return value, False
        except Exception as error:
            async with self._store_factory() as store:
                await store.fail_image_analysis(record_id, str(error))
                await store.commit()
            raise


def _city_name(value: str) -> str:
    normalized = value.strip()
    return normalized[:-1] if normalized.endswith("市") and len(normalized) > 2 else normalized


def _entity_type(value: str) -> str:
    if "餐饮" in value or "餐厅" in value:
        return "restaurant"
    if "住宿" in value or "酒店" in value:
        return "hotel"
    if any(word in value for word in ("车站", "机场", "交通")):
        return "transport_hub"
    return "attraction"


def _float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
