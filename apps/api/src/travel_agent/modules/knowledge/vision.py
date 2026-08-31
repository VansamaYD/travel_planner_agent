from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlparse

import httpx

from travel_agent.modules.knowledge.domain import VisionUnavailableError


class DeepSeekVisionProvider:
    prompt_version = "travel-image-v1"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: int,
        enabled: bool,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.model_name, self.timeout_seconds = model_name, timeout_seconds
        self.enabled, self.transport = enabled, transport

    async def analyze(self, source_url: str, mode: str) -> dict[str, object]:
        _validate_public_image_url(source_url)
        if not self.enabled or not self.api_key or not self.model_name:
            raise VisionUnavailableError("视觉模型未启用或未配置。")
        prompt = (
            "你是旅行资料图像整理器。判断图片属于攻略信息页还是普通地点照片。"
            "攻略信息页需完整提取可见文字并整理路线、地点、营业时间、预约、项目、价格、美食和注意事项;"
            "普通照片只生成准确简短描述和便于归档的中文文件名。"
            "不要猜测看不清的信息。仅返回 JSON 对象, 字段为 image_kind、suggested_filename、"
            "transcription、description、places、facts、confidence。"
            f"用户指定模式: {mode}。"
        )
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self.transport
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": source_url,
                                        "detail": "high" if mode != "place_photo" else "low",
                                    },
                                },
                            ],
                        }
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 4096,
                    "stream": False,
                },
            )
            response.raise_for_status()
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
            result = json.loads(_strip_fence(str(content)))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise VisionUnavailableError("视觉模型返回了无法解析的结果。") from error
        if not isinstance(result, dict):
            raise VisionUnavailableError("视觉模型结果不是对象。")
        return {str(key): value for key, value in result.items()}


class DisabledVisionProvider:
    prompt_version = "travel-image-v1"
    model_name = "disabled"

    async def analyze(self, source_url: str, mode: str) -> dict[str, object]:
        raise VisionUnavailableError("视觉模型未启用。")


def _validate_public_image_url(value: str) -> None:
    if len(value) > 8192:
        raise VisionUnavailableError("图片地址过长。")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise VisionUnavailableError("仅支持公开 HTTP/HTTPS 图片地址。")
    hostname = parsed.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise VisionUnavailableError("不允许分析本地网络地址。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise VisionUnavailableError("不允许分析内网或保留地址。")


def _strip_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped
