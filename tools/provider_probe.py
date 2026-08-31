#!/usr/bin/env python3
"""Live, secret-safe capability probes for configured travel providers.

The probe intentionally records only status, latency, selected field names and
short error categories. It never writes request headers, API keys, full URLs
with query strings, or provider response bodies to the report.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


ENV = {**load_dotenv(ROOT / ".env"), **os.environ}


def env(name: str, default: str = "") -> str:
    return ENV.get(name, default).strip()


def parse_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class ProbeResult:
    provider: str
    operation: str
    status: str
    latency_ms: int | None = None
    http_status: int | None = None
    provider_code: str | None = None
    fields_present: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "fields_present": self.fields_present,
            "notes": self.notes,
            "secrets_redacted": True,
        }


RESULTS: list[ProbeResult] = []


def add(result: ProbeResult) -> None:
    RESULTS.append(result)
    marker = {"passed": "PASS", "partial": "PART", "skipped": "SKIP"}.get(
        result.status, "FAIL"
    )
    latency = f" {result.latency_ms}ms" if result.latency_ms is not None else ""
    print(f"[{marker}] {result.provider}.{result.operation}{latency}", flush=True)


def missing(provider: str, operation: str, variables: list[str]) -> None:
    add(
        ProbeResult(
            provider,
            operation,
            "skipped",
            notes=["missing configuration: " + ", ".join(variables)],
        )
    )


def sanitize_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"network error: {type(exc.reason).__name__}"
    if isinstance(exc, TimeoutError):
        return "timeout"
    return type(exc).__name__


def request_json(
    method: str,
    base_url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any], int]:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = base_url + (("&" if "?" in base_url else "?") + query if query else "")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req_headers = {"Accept": "application/json", "User-Agent": "travel-planner-probe/0.1"}
    req_headers.update(headers or {})
    if body is not None:
        req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(2_000_000)
        encoding = response.headers.get("Content-Encoding", "").lower()
        if encoding == "gzip" or payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        elif encoding == "deflate":
            payload = zlib.decompress(payload)
        latency_ms = round((time.monotonic() - started) * 1000)
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return response.status, parsed, latency_ms


def request_text(
    url: str, *, headers: dict[str, str] | None = None, timeout: int = 30
) -> tuple[int, str, int]:
    req_headers = {"User-Agent": "travel-planner-probe/0.1"}
    req_headers.update(headers or {})
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(2_000_000).decode("utf-8", errors="replace")
        return response.status, payload, round((time.monotonic() - started) * 1000)


def split_lon_lat() -> tuple[str, str, str, str]:
    origin = env("INTEGRATION_TEST_ORIGIN", "116.397499,39.908722")
    destination = env("INTEGRATION_TEST_DESTINATION", "116.481028,39.989643")
    origin_lon, origin_lat = [part.strip() for part in origin.split(",", 1)]
    dest_lon, dest_lat = [part.strip() for part in destination.split(",", 1)]
    return origin_lon, origin_lat, dest_lon, dest_lat


def probe_deepseek() -> None:
    api_key = env("DEEPSEEK_API_KEY")
    base_url = env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = env("DEEPSEEK_MODEL")
    if not api_key or not model:
        missing("deepseek", "all", [name for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL") if not env(name)])
        return

    endpoint = base_url + "/chat/completions"
    auth = {"Authorization": f"Bearer {api_key}"}

    cases: list[tuple[str, dict[str, Any]]] = [
        (
            "chat",
            {
                "model": model,
                "messages": [{"role": "user", "content": "只回复两个大写字母：OK"}],
                "max_tokens": 32,
                "stream": False,
            },
        ),
        (
            "json_object",
            {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": '输出 JSON，且只包含 {"provider":"deepseek","status":"ok"}',
                    }
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 96,
                "stream": False,
            },
        ),
        (
            "tool_call",
            {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": "必须调用 get_weather 工具查询北京天气，不要直接回答。",
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "查询指定城市天气",
                            "parameters": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
                "max_tokens": 128,
                "stream": False,
            },
        ),
    ]

    for operation, body in cases:
        try:
            status, payload, latency = request_json(
                "POST", endpoint, headers=auth, body=body, timeout=int(env("MODEL_TEST_TIMEOUT_SECONDS", "120"))
            )
            choice = (payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            usage = payload.get("usage") or {}
            fields = [name for name in ("id", "model", "choices", "usage") if name in payload]
            notes: list[str] = []
            result_status = "passed"
            if operation == "json_object":
                try:
                    parsed_content = json.loads(message.get("content") or "")
                    if parsed_content.get("status") != "ok":
                        result_status = "partial"
                        notes.append("valid JSON returned but expected field value differed")
                except (json.JSONDecodeError, AttributeError):
                    result_status = "failed"
                    notes.append("response_format did not produce valid JSON")
            if operation == "tool_call":
                calls = message.get("tool_calls") or []
                if not calls:
                    result_status = "failed"
                    notes.append("no tool_calls returned")
                else:
                    fields.append("tool_calls")
                    try:
                        json.loads(calls[0]["function"]["arguments"])
                    except (KeyError, TypeError, json.JSONDecodeError):
                        result_status = "partial"
                        notes.append("tool arguments were not valid JSON")
            if usage:
                fields.append("usage_tokens")
            add(ProbeResult("deepseek", operation, result_status, latency, status, fields_present=sorted(set(fields)), notes=notes))
        except Exception as exc:  # noqa: BLE001 - probe must continue
            add(ProbeResult("deepseek", operation, "failed", notes=[sanitize_error(exc)]))

    try:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "只回复：STREAM_OK"}],
            "max_tokens": 48,
            "stream": True,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={**auth, "Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        started = time.monotonic()
        event_count = 0
        content_count = 0
        with urllib.request.urlopen(request, timeout=int(env("MODEL_TEST_TIMEOUT_SECONDS", "120"))) as response:
            http_status = response.status
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event_count += 1
                item = json.loads(data)
                delta = ((item.get("choices") or [{}])[0].get("delta") or {})
                if delta.get("content") or delta.get("reasoning_content"):
                    content_count += 1
        latency = round((time.monotonic() - started) * 1000)
        status_name = "passed" if event_count and content_count else "partial"
        add(
            ProbeResult(
                "deepseek",
                "stream",
                status_name,
                latency,
                http_status,
                fields_present=["sse_events", "content_delta"] if content_count else ["sse_events"],
                notes=[f"events={event_count}, content_events={content_count}"],
            )
        )
    except Exception as exc:  # noqa: BLE001
        add(ProbeResult("deepseek", "stream", "failed", notes=[sanitize_error(exc)]))


def probe_amap() -> None:
    key = env("AMAP_WEB_SERVICE_KEY")
    if not key:
        missing("amap", "web_service", ["AMAP_WEB_SERVICE_KEY"])
        return
    origin_lon, origin_lat, dest_lon, dest_lat = split_lon_lat()
    cases = [
        (
            "geocode",
            "https://restapi.amap.com/v3/geocode/geo",
            {"address": "天安门", "city": "北京", "key": key},
            "geocodes",
        ),
        (
            "place_text_v5",
            "https://restapi.amap.com/v5/place/text",
            {"keywords": "故宫博物院", "region": "110000", "key": key},
            "pois",
        ),
        (
            "route_driving_v5",
            "https://restapi.amap.com/v5/direction/driving",
            {"origin": f"{origin_lon},{origin_lat}", "destination": f"{dest_lon},{dest_lat}", "key": key, "show_fields": "cost,navi"},
            "route",
        ),
        (
            "weather",
            "https://restapi.amap.com/v3/weather/weatherInfo",
            {"city": "110101", "extensions": "all", "key": key},
            "forecasts",
        ),
    ]
    for operation, endpoint, params, expected in cases:
        try:
            status, payload, latency = request_json("GET", endpoint, params=params, timeout=20)
            provider_code = str(payload.get("infocode", "")) or None
            ok = str(payload.get("status")) == "1"
            fields = [name for name in ("status", "info", "infocode", "count", expected) if name in payload]
            notes: list[str] = []
            result_status = "passed" if ok and expected in payload else "failed"
            if operation == "route_driving_v5" and isinstance(payload.get("route"), dict):
                route = payload["route"]
                paths = route.get("paths") or []
                if paths:
                    path = paths[0]
                    for name in ("distance", "duration", "cost", "tolls", "toll_distance"):
                        if name in path:
                            fields.append(f"path.{name}")
                else:
                    notes.append("no route paths returned")
            add(ProbeResult("amap", operation, result_status, latency, status, provider_code, sorted(set(fields)), notes))
        except Exception as exc:  # noqa: BLE001
            add(ProbeResult("amap", operation, "failed", notes=[sanitize_error(exc)]))

    js_key = env("AMAP_JS_API_KEY")
    security_key = env("AMAP_JS_SECURITY_KEY")
    if not js_key or not security_key:
        missing("amap", "js_api_load", [name for name in ("AMAP_JS_API_KEY", "AMAP_JS_SECURITY_KEY") if not env(name)])
    else:
        try:
            url = "https://webapi.amap.com/maps?" + urllib.parse.urlencode({"v": "2.0", "key": js_key})
            status, text, latency = request_text(url, headers={"Referer": env("APP_BASE_URL", "http://localhost:8000")}, timeout=20)
            ok = status == 200 and len(text) > 1000
            add(
                ProbeResult(
                    "amap",
                    "js_api_load",
                    "partial" if ok else "failed",
                    latency,
                    status,
                    fields_present=["javascript_payload", "security_key_configured"] if ok else [],
                    notes=["script loaded; browser/domain-whitelist rendering still required"] if ok else ["script payload was unexpectedly small"],
                )
            )
        except Exception as exc:  # noqa: BLE001
            add(ProbeResult("amap", "js_api_load", "failed", notes=[sanitize_error(exc)]))


def probe_baidu() -> None:
    ak = env("BAIDU_MAP_SERVER_AK")
    if not ak:
        missing("baidu_map", "server", ["BAIDU_MAP_SERVER_AK"])
        return
    origin_lon, origin_lat, dest_lon, dest_lat = split_lon_lat()
    cases = [
        (
            "geocode",
            "https://api.map.baidu.com/geocoding/v3/",
            {"address": "天安门", "city": "北京市", "output": "json", "ak": ak},
            "result",
        ),
        (
            "place_region_v3",
            "https://api.map.baidu.com/place/v3/region",
            {"query": "故宫博物院", "region": "北京市", "output": "json", "ak": ak},
            "results",
        ),
        (
            "route_driving_v2",
            "https://api.map.baidu.com/direction/v2/driving",
            {
                "origin": f"{origin_lat},{origin_lon}",
                "destination": f"{dest_lat},{dest_lon}",
                "coord_type": "wgs84",
                "ret_coordtype": "gcj02",
                "output": "json",
                "ak": ak,
            },
            "result",
        ),
    ]
    for operation, endpoint, params, expected in cases:
        try:
            status, payload, latency = request_json("GET", endpoint, params=params, timeout=20)
            provider_code = str(payload.get("status", ""))
            ok = provider_code == "0" and expected in payload
            fields = [name for name in ("status", "message", expected) if name in payload]
            notes: list[str] = []
            if not env("BAIDU_MAP_SERVER_SK"):
                notes.append("AK-only request; SERVER_SK not required for this successful mode" if ok else "SERVER_SK empty; inspect AK authentication restrictions if request failed")
            add(ProbeResult("baidu_map", operation, "passed" if ok else "failed", latency, status, provider_code, fields, notes))
        except Exception as exc:  # noqa: BLE001
            add(ProbeResult("baidu_map", operation, "failed", notes=[sanitize_error(exc), "SERVER_SK is empty; verify AK type and restrictions if applicable"]))

    js_ak = env("BAIDU_MAP_JS_AK")
    if not js_ak:
        missing("baidu_map", "js_api_load", ["BAIDU_MAP_JS_AK"])
    else:
        try:
            url = "https://api.map.baidu.com/api?" + urllib.parse.urlencode({"v": "3.0", "type": "webgl", "ak": js_ak})
            status, text, latency = request_text(url, headers={"Referer": env("APP_BASE_URL", "http://localhost:8000")}, timeout=20)
            ok = status == 200 and len(text) > 100
            add(
                ProbeResult(
                    "baidu_map",
                    "js_api_load",
                    "partial" if ok else "failed",
                    latency,
                    status,
                    fields_present=["javascript_payload"] if ok else [],
                    notes=["script loaded; browser/Referer-whitelist rendering still required"] if ok else ["script payload was unexpectedly small"],
                )
            )
        except Exception as exc:  # noqa: BLE001
            add(ProbeResult("baidu_map", "js_api_load", "failed", notes=[sanitize_error(exc)]))


def qweather_host() -> str:
    host = env("QWEATHER_API_HOST")
    if host and not host.startswith(("http://", "https://")):
        host = "https://" + host
    return host.rstrip("/")


def probe_qweather() -> None:
    host = qweather_host()
    key = env("QWEATHER_API_KEY")
    if not host or not key:
        missing("qweather", "all", [name for name, value in (("QWEATHER_API_HOST", host), ("QWEATHER_API_KEY", key)) if not value])
        return
    origin_lon, origin_lat, _, _ = split_lon_lat()
    # Use two decimal places as required by the current coordinate-based API.
    lat_text = f"{float(origin_lat):.2f}"
    lon_text = f"{float(origin_lon):.2f}"
    headers = {"X-QW-Api-Key": key}
    cases = [
        ("daily_forecast", f"{host}/weather/v1/daily/{lat_text}/{lon_text}", {"days": 3, "localTime": "true", "lang": "zh"}, "days"),
        ("weather_alert", f"{host}/weatheralert/v1/current/{lat_text}/{lon_text}", {"localTime": "true", "lang": "zh"}, "alerts"),
    ]
    for operation, endpoint, params, expected in cases:
        try:
            status, payload, latency = request_json("GET", endpoint, params=params, headers=headers, timeout=20)
            fields = [name for name in ("metadata", expected) if name in payload]
            ok = status == 200 and expected in payload
            add(ProbeResult("qweather", operation, "passed" if ok else "failed", latency, status, fields_present=fields))
        except urllib.error.HTTPError as exc:
            legacy = {
                "daily_forecast": ("/v7/weather/3d", "daily"),
                "weather_alert": ("/v7/warning/now", "warning"),
            }.get(operation)
            if legacy and exc.code in {400, 401, 403, 404}:
                # Compatibility fallback for API v7 credentials/hosts.
                try:
                    status, payload, latency = request_json(
                        "GET",
                        f"{host}{legacy[0]}",
                        params={"location": f"{lon_text},{lat_text}", "lang": "zh"},
                        headers=headers,
                        timeout=20,
                    )
                    code = str(payload.get("code", ""))
                    ok = code == "200" and legacy[1] in payload
                    add(
                        ProbeResult(
                            "qweather",
                            operation,
                            "passed" if ok else "failed",
                            latency,
                            status,
                            code,
                            [name for name in ("code", "updateTime", "fxLink", legacy[1]) if name in payload],
                            [f"credential/host uses compatible v7 endpoint ({legacy[1]})"],
                        )
                    )
                    continue
                except Exception as fallback_exc:  # noqa: BLE001
                    add(ProbeResult("qweather", operation, "failed", notes=[sanitize_error(exc), "v7 fallback: " + sanitize_error(fallback_exc)]))
                    continue
            add(ProbeResult("qweather", operation, "failed", http_status=exc.code, notes=[sanitize_error(exc)]))
        except Exception as exc:  # noqa: BLE001
            add(ProbeResult("qweather", operation, "failed", notes=[sanitize_error(exc)]))


def probe_smtp() -> None:
    host = env("SMTP_HOST")
    username = env("SMTP_USERNAME")
    password = env("SMTP_PASSWORD")
    if not host:
        missing("smtp", "connect_auth", ["SMTP_HOST"])
        return
    port = int(env("SMTP_PORT", "587"))
    use_tls = parse_bool(env("SMTP_USE_TLS", "true"), True)
    started = time.monotonic()
    try:
        context = ssl.create_default_context()
        if port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=20)
        with client:
            client.ehlo()
            fields = ["connect", "ehlo"]
            if use_tls and port != 465:
                client.starttls(context=context)
                client.ehlo()
                fields.append("starttls")
            elif port == 465:
                fields.append("implicit_tls")
            if username and password:
                client.login(username, password)
                fields.append("auth")
            else:
                fields.append("auth_not_tested")
        latency = round((time.monotonic() - started) * 1000)
        add(ProbeResult("smtp", "connect_auth", "passed", latency, fields_present=fields, notes=["no email was sent"]))
    except Exception as exc:  # noqa: BLE001
        add(ProbeResult("smtp", "connect_auth", "failed", notes=[sanitize_error(exc), "no email was sent"]))


def render_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for result in RESULTS:
        counts[result.status] = counts.get(result.status, 0) + 1
    lines = [
        "# Provider 联网能力探测报告",
        "",
        f"> 生成时间：{now_iso()}  ",
        "> 报告已脱敏：不包含 API Key、Authorization Header、SMTP 密码或完整响应正文。",
        "",
        "## 摘要",
        "",
        f"- 通过：{counts.get('passed', 0)}",
        f"- 部分通过/需浏览器复核：{counts.get('partial', 0)}",
        f"- 失败：{counts.get('failed', 0)}",
        f"- 跳过：{counts.get('skipped', 0)}",
        "",
        "## 结果",
        "",
        "| Provider | Operation | 状态 | HTTP | 延迟 | Provider Code | 已确认字段 | 说明 |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for item in RESULTS:
        labels = {"passed": "通过", "partial": "部分通过", "failed": "失败", "skipped": "跳过"}
        notes = "; ".join(item.notes).replace("|", "\\|")
        fields = ", ".join(item.fields_present).replace("|", "\\|")
        lines.append(
            f"| {item.provider} | {item.operation} | {labels.get(item.status, item.status)} | "
            f"{item.http_status or ''} | {str(item.latency_ms) + ' ms' if item.latency_ms is not None else ''} | "
            f"{item.provider_code or ''} | {fields} | {notes} |"
        )
    lines.extend(
        [
            "",
            "## 解释",
            "",
            "- JS API 的“部分通过”只表示脚本服务可以加载且密钥已配置；地图渲染、Referer/域名白名单和手机唤端仍需浏览器验收。",
            "- 地图路线费用字段只表示当前样例是否返回，不能视为所有城市、路线和账号永久保证。",
            "- SMTP 探测只连接、TLS 和登录，不发送测试邮件。",
            "- 失败项只记录脱敏错误类型；需要排障时应在本机查看 Provider 控制台，不要复制包含 Key 的完整 URL。",
            "",
            "## 机器可读结果",
            "",
            "```json",
            json.dumps({"generated_at": now_iso(), "results": [item.as_dict() for item in RESULTS]}, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="confirm that real provider calls are intended")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "data" / "integration-reports" / "provider-probe-latest.md",
    )
    parser.add_argument(
        "--providers",
        default="deepseek,amap,baidu,qweather,smtp",
        help="comma-separated subset: deepseek,amap,baidu,qweather,smtp",
    )
    args = parser.parse_args()
    if not args.live:
        print("Refusing live calls without --live", file=sys.stderr)
        return 2

    selected = {item.strip().lower() for item in args.providers.split(",") if item.strip()}
    probes = {
        "deepseek": probe_deepseek,
        "amap": probe_amap,
        "baidu": probe_baidu,
        "qweather": probe_qweather,
        "smtp": probe_smtp,
    }
    unknown = selected - probes.keys()
    if unknown:
        parser.error("unknown providers: " + ", ".join(sorted(unknown)))
    for name, probe in probes.items():
        if name in selected:
            probe()
    render_report(args.report)
    print(f"Report: {args.report}")
    failed = sum(item.status == "failed" for item in RESULTS)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
