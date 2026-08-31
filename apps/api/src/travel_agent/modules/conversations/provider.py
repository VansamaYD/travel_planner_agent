from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class DeepSeekChatProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
        max_output_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key, self._base_url, self._model, self._timeout = (
            api_key,
            base_url.rstrip("/"),
            model,
            timeout,
        )
        self._transport = transport
        self._max_output_tokens = max_output_tokens

    async def stream(self, messages: tuple[tuple[str, str], ...]) -> AsyncIterator[str]:
        if not self._key or not self._model:
            raise RuntimeError("model is not configured")
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是私有部署的旅行助手. 优先用简洁中文回答, "
                        "明确区分事实、估算和建议. "
                        "当缺少地图、天气或实时价格工具结果时, "
                        "不得声称已经联网核验."
                    ),
                },
                *({"role": role, "content": content} for role, content in messages),
            ],
            "stream": True,
            "temperature": 0.4,
            "max_tokens": self._max_output_tokens,
        }
        async with (
            httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
            client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                value = json.loads(line[6:])
                delta = value.get("choices", [{}])[0].get("delta", {}).get("content")
                if isinstance(delta, str) and delta:
                    yield delta


class DisabledChatProvider:
    async def stream(self, messages: tuple[tuple[str, str], ...]) -> AsyncIterator[str]:
        if False:
            yield ""
        raise RuntimeError("model is not configured")
