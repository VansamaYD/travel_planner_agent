from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from travel_agent.bootstrap.settings import Settings


class TextProtector(Protocol):
    def encrypt(self, plaintext: str, *, context: str) -> bytes: ...
    def decrypt(self, ciphertext: bytes, *, context: str) -> str: ...


@dataclass(frozen=True, slots=True)
class IntegrationField:
    key: str
    label: str
    group: str
    kind: str = "text"
    secret: bool = False
    implemented: bool = True


INTEGRATION_FIELDS = (
    IntegrationField("deepseek_api_key", "DeepSeek API Key", "模型", "password", True),
    IntegrationField("deepseek_base_url", "DeepSeek Base URL", "模型", "url"),
    IntegrationField("deepseek_model", "默认对话模型", "模型"),
    IntegrationField("vision_analysis_enabled", "启用视觉分析", "模型", "boolean"),
    IntegrationField("deepseek_vision_model", "视觉模型", "模型"),
    IntegrationField("amap_web_service_key", "高德 Web Service Key", "地图", "password", True),
    IntegrationField("amap_js_api_key", "高德 JS API Key", "地图", "password", True),
    IntegrationField("amap_js_security_key", "高德 JS 安全密钥", "地图", "password", True),
    IntegrationField("baidu_map_server_ak", "百度地图 Server AK", "地图", "password", True, False),
    IntegrationField("baidu_map_server_sk", "百度地图 Server SK", "地图", "password", True, False),
    IntegrationField("baidu_map_js_ak", "百度地图 JS AK", "地图", "password", True, False),
    IntegrationField("qweather_api_host", "和风天气 API Host", "天气", "url"),
    IntegrationField("qweather_api_key", "和风天气 API Key", "天气", "password", True),
    IntegrationField("xhs_research_enabled", "启用小红书只读研究", "攻略", "boolean"),
    IntegrationField("xhs_mcp_endpoint", "小红书 MCP 地址", "攻略", "url"),
    IntegrationField("smtp_host", "SMTP 主机", "通知", implemented=False),
    IntegrationField("smtp_port", "SMTP 端口", "通知", "number", implemented=False),
    IntegrationField("smtp_username", "SMTP 用户名", "通知", implemented=False),
    IntegrationField("smtp_password", "SMTP 密码/授权码", "通知", "password", True, False),
    IntegrationField("smtp_use_tls", "SMTP TLS", "通知", "boolean", implemented=False),
    IntegrationField("smtp_from_address", "发件地址", "通知", implemented=False),
)

_FIELDS = {field.key: field for field in INTEGRATION_FIELDS}
_CONTEXT = "runtime.integration.config"


class EncryptedRuntimeConfig:
    def __init__(self, config_root: Path, protector: TextProtector) -> None:
        self._root = config_root
        self._path = config_root / "runtime-integrations.enc"
        self._protector = protector

    def load(self) -> dict[str, object]:
        try:
            raw = self._protector.decrypt(self._path.read_bytes(), context=_CONTEXT)
        except FileNotFoundError:
            return {}
        value = json.loads(raw)
        if not isinstance(value, dict):
            return {}
        return {
            key: item
            for key, item in value.items()
            if key in _FIELDS and isinstance(item, (str, int, bool))
        }

    def save(self, changes: dict[str, object | None]) -> dict[str, object]:
        values = self.load()
        for key, value in changes.items():
            field = _FIELDS.get(key)
            if field is None:
                raise ValueError(f"不支持的配置项: {key}")
            if value is None:
                values.pop(key, None)
                continue
            values[key] = _normalize(field, value)
        self._root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        temporary = self._path.with_suffix(".tmp")
        temporary.write_bytes(self._protector.encrypt(payload, context=_CONTEXT))
        os.chmod(temporary, 0o600)
        temporary.replace(self._path)
        return values

    def describe(self, settings: Settings) -> tuple[dict[str, object], ...]:
        overrides = self.load()
        result = []
        for field in INTEGRATION_FIELDS:
            value = getattr(settings, field.key)
            if hasattr(value, "get_secret_value"):
                value = value.get_secret_value()
            configured = value not in (None, "", False)
            result.append(
                {
                    "key": field.key,
                    "label": field.label,
                    "group": field.group,
                    "kind": field.kind,
                    "secret": field.secret,
                    "configured": configured,
                    "value": "" if field.secret else value,
                    "source": "settings" if field.key in overrides else "environment",
                    "implemented": field.implemented,
                }
            )
        return tuple(result)


def apply_runtime_config(settings: Settings, config: EncryptedRuntimeConfig) -> Settings:
    overrides = config.load()
    if not overrides:
        return settings
    return Settings.model_validate({**settings.model_dump(), **overrides})


def _normalize(field: IntegrationField, value: object) -> object:
    if field.kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{field.label} 必须是布尔值")
        return value
    if field.kind == "number":
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
            raise ValueError(f"{field.label} 数值无效")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field.label} 必须是文本")
    clean = value.strip()
    if len(clean) > 8192:
        raise ValueError(f"{field.label} 内容过长")
    return clean
