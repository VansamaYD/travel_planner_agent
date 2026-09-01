import json

import httpx
import pytest

from travel_agent.modules.knowledge.domain import VisionUnavailableError
from travel_agent.modules.knowledge.vision import DeepSeekVisionProvider


@pytest.mark.asyncio
async def test_vision_provider_retries_transport_failures() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("temporary DNS failure", request=request)
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash-vision-exp"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"image_kind": "guide_page", "confidence": 0.9})
                        }
                    }
                ]
            },
        )

    provider = DeepSeekVisionProvider(
        "test-key",
        "https://api.deepseek.com",
        "deepseek-v4-flash-vision-exp",
        10,
        True,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.analyze("https://img.example/guide.jpg", "guide_page")

    assert calls == 3
    assert result["image_kind"] == "guide_page"


@pytest.mark.asyncio
async def test_vision_provider_maps_non_retryable_http_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "invalid image"}})

    provider = DeepSeekVisionProvider(
        "test-key",
        "https://api.deepseek.com",
        "deepseek-v4-flash-vision-exp",
        10,
        True,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(VisionUnavailableError, match="无法处理"):
        await provider.analyze("https://img.example/guide.jpg", "guide_page")
