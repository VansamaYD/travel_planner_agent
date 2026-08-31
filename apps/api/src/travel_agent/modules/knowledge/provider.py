from __future__ import annotations

from travel_agent.modules.knowledge.service import KnowledgeService
from travel_agent.modules.tools.domain import ToolInputError


class PlaceKnowledgeProvider:
    name = "local_place_knowledge"

    def __init__(self, service: KnowledgeService) -> None:
        self._service = service

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        if not owner_user_id:
            raise ToolInputError("地点知识库检索请求无效。")
        if operation == "place_knowledge_upsert":
            try:
                value = await self._service.upsert_agent_claim(owner_user_id, args)
            except ValueError as error:
                raise ToolInputError(str(error)) from error
            return {
                "card_id": value.id,
                "name": value.name,
                "city": value.city,
                "version": value.version,
                "status": "knowledge_updated",
            }
        if operation == "place_knowledge_batch_upsert":
            claims = args.get("cards")
            if not isinstance(claims, list) or not 1 <= len(claims) <= 8:
                raise ToolInputError("批量地点卡必须包含 1 至 8 项。")
            cards = []
            for index, claim in enumerate(claims, start=1):
                if not isinstance(claim, dict):
                    raise ToolInputError(f"第 {index} 项地点卡参数无效。")
                try:
                    value = await self._service.upsert_agent_claim(owner_user_id, claim)
                except ValueError as error:
                    raise ToolInputError(f"第 {index} 项: {error}") from error
                cards.append(
                    {
                        "card_id": value.id,
                        "name": value.name,
                        "city": value.city,
                        "version": value.version,
                        "status": "knowledge_updated",
                    }
                )
            return {"cards": cards, "status": "knowledge_batch_updated"}
        if operation != "place_knowledge_search":
            raise ToolInputError("地点知识库工具不支持该操作。")
        query = str(args.get("query") or "").strip()
        city = str(args.get("city") or "").strip()
        if not query or len(query) > 200 or len(city) > 100:
            raise ToolInputError("地点知识库关键词无效。")
        values = await self._service.list_places(owner_user_id, query, city)
        return {
            "query": query,
            "city": city,
            "cards": [
                {
                    "card_id": value.id,
                    "entity_type": value.entity_type,
                    "name": value.name,
                    "city": value.city,
                    "address": value.address,
                    "intro": value.intro,
                    "longitude": value.longitude,
                    "latitude": value.latitude,
                    "details": value.details,
                    "confidence": value.confidence,
                    "version": value.version,
                    "last_verified_at": value.last_verified_at.isoformat()
                    if value.last_verified_at
                    else None,
                    "expires_at": value.expires_at.isoformat() if value.expires_at else None,
                }
                for value in values[:8]
            ],
            "source": "private_place_knowledge",
        }
