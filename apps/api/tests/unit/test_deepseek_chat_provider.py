import json

import httpx
import pytest

from travel_agent.modules.conversations.provider import DeepSeekChatProvider


@pytest.mark.asyncio
async def test_chat_provider_streams_only_visible_answer_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["max_tokens"] == 4096
        assert payload["messages"][-1] == {"role": "user", "content": "你好"}
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )

    provider = DeepSeekChatProvider(
        "test-key",
        "https://api.deepseek.com/",
        "deepseek-chat",
        30,
        4096,
        transport=httpx.MockTransport(handler),
    )
    chunks = [chunk async for chunk in provider.stream((("user", "你好"),))]
    assert chunks == ["你", "好"]
