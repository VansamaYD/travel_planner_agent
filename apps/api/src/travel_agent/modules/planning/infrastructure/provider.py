from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from travel_agent.modules.planning.application.errors import (
    PlanningProviderError,
    PlanningProviderUnavailableError,
)
from travel_agent.modules.planning.domain.models import ModelUsage


@dataclass(frozen=True, slots=True)
class DeepSeekResult:
    days: tuple[dict[str, object], ...]
    summary: str
    rationale: str
    warnings: tuple[str, ...]
    usage: ModelUsage


class DeepSeekProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        max_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key, self._base_url, self._model = api_key, base_url.rstrip("/"), model
        self._timeout, self._max_tokens = timeout_seconds, max_tokens
        self._transport = transport

    async def generate_itinerary(self, context: dict[str, object]) -> DeepSeekResult:
        if not self._api_key or not self._model:
            raise PlanningProviderUnavailableError("DeepSeek API Key 或模型尚未配置。")
        request = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False, default=str)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request,
                )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            value = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise PlanningProviderError("DeepSeek 返回失败或不是有效 JSON。") from error
        days = self._validate(value.get("days"))
        usage_raw = payload.get("usage") or {}
        input_tokens = int(usage_raw.get("prompt_tokens", 0))
        output_tokens = int(usage_raw.get("completion_tokens", 0))
        cache_hit = int(usage_raw.get("prompt_cache_hit_tokens", 0))
        usage = ModelUsage(
            input_tokens,
            output_tokens,
            cache_hit,
            self._estimate(input_tokens, output_tokens, cache_hit),
        )
        return DeepSeekResult(
            days=days,
            summary=str(value.get("summary", "AI 旅行计划提案"))[:500],
            rationale=str(value.get("rationale", ""))[:2000],
            warnings=tuple(str(item)[:300] for item in value.get("warnings", [])[:20]),
            usage=usage,
        )

    @staticmethod
    def _validate(raw: object) -> tuple[dict[str, object], ...]:
        if not isinstance(raw, list) or not 1 <= len(raw) <= 60:
            raise PlanningProviderError("模型日程天数不符合约束。")
        days: list[dict[str, object]] = []
        for day in raw:
            if not isinstance(day, dict) or not isinstance(day.get("local_date"), str):
                raise PlanningProviderError("模型日程日期字段无效。")
            items = day.get("items", [])
            if not isinstance(items, list) or len(items) > 40:
                raise PlanningProviderError("模型单日活动数量无效。")
            normalized_items: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict) or not str(item.get("title", "")).strip():
                    raise PlanningProviderError("模型活动缺少标题。")
                item_type = str(item.get("item_type", "other"))
                if item_type not in {
                    "place",
                    "restaurant",
                    "hotel",
                    "rest",
                    "transport",
                    "free_time",
                    "other",
                }:
                    item_type = "other"
                normalized_items.append(
                    {
                        "logical_id": None,
                        "item_type": item_type,
                        "title": str(item["title"])[:120],
                        "place_name": str(item.get("place_name", ""))[:160],
                        "start_time": DeepSeekProvider._time(item.get("start_time")),
                        "end_time": DeepSeekProvider._time(item.get("end_time")),
                        "cost_cents": DeepSeekProvider._non_negative_int(item.get("cost_cents")),
                        "execution_status": "candidate",
                        "notes": str(item.get("notes", ""))[:1000],
                        "tags": DeepSeekProvider._tags(item.get("tags")),
                        "transport_to_next": DeepSeekProvider._optional_text(
                            item.get("transport_to_next"), 80
                        ),
                        "travel_minutes_to_next": DeepSeekProvider._non_negative_int(
                            item.get("travel_minutes_to_next")
                        ),
                        "travel_cost_cents_to_next": DeepSeekProvider._non_negative_int(
                            item.get("travel_cost_cents_to_next")
                        ),
                    }
                )
            days.append(
                {
                    "id": None,
                    "local_date": day["local_date"],
                    "city": str(day.get("city", "待定城市"))[:120],
                    "summary": str(day.get("summary", ""))[:500],
                    "items": normalized_items,
                }
            )
        return tuple(days)

    @staticmethod
    def _time(value: object) -> str | None:
        text = str(value) if value is not None else ""
        return text if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) else None

    @staticmethod
    def _non_negative_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            result = value
        elif isinstance(value, str):
            try:
                result = int(value)
            except ValueError:
                return None
        else:
            return None
        return result if result >= 0 else None

    @staticmethod
    def _optional_text(value: object, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:limit] if text else None

    @staticmethod
    def _tags(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(tag)[:40] for tag in value[:20] if str(tag).strip()]

    def _estimate(self, input_tokens: int, output_tokens: int, cache_hit: int) -> int:
        peak = datetime.now(UTC).hour in {1, 2, 3, 6, 7, 8, 9}
        if "pro" in self._model.lower():
            hit, miss, output = (0.044, 1.32, 3.96) if peak else (0.022, 0.66, 1.98)
        elif "flash" in self._model.lower():
            hit, miss, output = (0.014, 0.44, 1.32) if peak else (0.007, 0.22, 0.66)
        else:
            return 0
        miss_tokens = max(input_tokens - cache_hit, 0)
        return round(cache_hit * hit + miss_tokens * miss + output_tokens * output)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是旅行日程设计节点, 只输出 JSON 对象. "
            "根据已确认需求生成按天候选计划, 不声称价格、营业时间或路线已核验. "
            '格式: {"summary":string,"rationale":string,"warnings":[string],'
            '"days":[{"local_date":"YYYY-MM-DD","city":string,'
            '"summary":string,"items":[{"item_type":'
            '"place|restaurant|hotel|rest|transport|free_time|other",'
            '"title":string,"place_name":string,"start_time":"HH:MM"或null,'
            '"end_time":"HH:MM"或null,"cost_cents":整数或null,'
            '"notes":string,"tags":[string],"transport_to_next":string或null,'
            '"travel_minutes_to_next":整数或null,'
            '"travel_cost_cents_to_next":整数或null}]}]}. '
            "必须覆盖旅行日期且遵守硬约束. 未知价格填 null."
        )


class DisabledModelProvider:
    async def generate_itinerary(self, context: dict[str, object]) -> DeepSeekResult:
        raise PlanningProviderUnavailableError("默认模型尚未配置。")
