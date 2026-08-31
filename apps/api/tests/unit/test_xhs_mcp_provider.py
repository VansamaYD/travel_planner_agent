import json

import httpx
import pytest

from travel_agent.modules.tools.providers import XiaohongshuMcpProvider


@pytest.mark.asyncio
async def test_xhs_connector_calls_only_read_search_tool_and_normalizes_links() -> None:
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {}},
                headers={"mcp-session-id": "session-1"},
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert payload["params"] == {"name": "search_feeds", "arguments": {"keyword": "苏州攻略"}}
        result = [
            {
                "id": "note-1",
                "xsecToken": "token-1",
                "noteCard": {
                    "displayTitle": "苏州两日游",
                    "desc": "园林路线",
                    "user": {"nickname": "A"},
                },
            }
        ]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                },
            },
        )

    provider = XiaohongshuMcpProvider(
        "http://worker:18060/mcp", 30, 8, transport=httpx.MockTransport(handler)
    )
    result = await provider.execute("guide_search_xhs", {"query": "苏州攻略"})
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    guides = result["guides"]
    assert isinstance(guides, list)
    assert guides[0]["title"] == "苏州两日游"
    assert guides[0]["url"].startswith("https://www.xiaohongshu.com/explore/note-1")
