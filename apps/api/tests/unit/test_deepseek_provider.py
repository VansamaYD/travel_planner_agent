import json

import httpx
import pytest

from travel_agent.modules.planning.infrastructure.provider import DeepSeekProvider


@pytest.mark.asyncio
async def test_deepseek_provider_uses_json_mode_and_normalizes_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["stream"] is False
        model_output = {
            "summary": "候选方案",
            "rationale": "减少折返",
            "warnings": ["价格待核验"],
            "days": [
                {
                    "local_date": "2026-10-02",
                    "city": "苏州",
                    "items": [
                        {
                            "item_type": "invented",
                            "title": "拙政园",
                            "start_time": "25:99",
                            "cost_cents": "8000",
                            "tags": "not-a-list",
                            "travel_minutes_to_next": -2,
                        }
                    ],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(model_output)}}],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "prompt_cache_hit_tokens": 200,
                },
            },
        )

    provider = DeepSeekProvider(
        "test-key",
        "https://api.deepseek.com/",
        "deepseek-v4-flash",
        30,
        4096,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_itinerary({"requirements": {"confirmed": True}})
    item = result.days[0]["items"][0]
    assert item["item_type"] == "other"
    assert item["start_time"] is None
    assert item["cost_cents"] == 8000
    assert item["tags"] == []
    assert item["travel_minutes_to_next"] is None
    assert result.usage.input_tokens == 1000
    assert result.usage.estimated_cost_microusd > 0
