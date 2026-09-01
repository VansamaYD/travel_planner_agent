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
    events = [
        event
        async for event in provider.stream_turn(
            ({"role": "user", "content": "你好"},),
            (),
        )
    ]
    assert [event.text for event in events if event.kind == "text"] == ["你", "好"]
    assert [event.text for event in events if event.kind == "reasoning"] == ["hidden"]


@pytest.mark.asyncio
async def test_chat_provider_aggregates_streamed_tool_call_arguments() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "tool_choice" not in payload
        assert payload["thinking"] == {"type": "enabled"}
        assert payload["tools"][0]["function"]["name"] == "place_search"
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"reasoning_content":"hidden-tool-reasoning"}}]}\n\n'
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
                '"function":{"name":"place_search","arguments":"{\\"query\\":"}}]}}]}\n\n'
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                '"function":{"arguments":"\\"拙政园\\"}"}}]}}]}\n\n'
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
    events = [
        event
        async for event in provider.stream_turn(
            ({"role": "user", "content": "查地点"},),
            (
                {
                    "type": "function",
                    "function": {"name": "place_search", "parameters": {"type": "object"}},
                },
            ),
        )
    ]
    call = next(event for event in events if event.kind == "tool_call")
    assert call.tool_call_id == "call-1"
    assert call.tool_name == "place_search"
    assert json.loads(call.tool_arguments) == {"query": "拙政园"}
