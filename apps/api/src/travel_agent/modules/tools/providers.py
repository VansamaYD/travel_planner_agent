from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlencode, urlparse

import httpx

from travel_agent.modules.tools.domain import ToolInputError, ToolUnavailableError
from travel_agent.modules.tools.store import SqlAlchemyToolStore


class AmapProvider:
    name = "amap"

    def __init__(
        self,
        api_key: str,
        timeout: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key, self._timeout, self._transport = api_key, timeout, transport

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        if not self._key:
            raise ToolUnavailableError("高德 Web Service Key 未配置。")
        if operation == "place_search":
            return await self._place_search(args)
        if operation == "route_quote":
            return await self._route_quote(args)
        raise ToolInputError("不支持的高德工具。")

    async def _place_search(self, args: dict[str, object]) -> dict[str, object]:
        query = _required_text(args, "query", 100)
        city = _optional_text(args, "city", 60)
        payload = await self._get(
            "/v3/place/text",
            {
                "keywords": query,
                "city": city,
                "citylimit": "true" if city else "false",
                "extensions": "all",
                "offset": "10",
                "page": "1",
            },
        )
        places = []
        for item in _list(payload.get("pois"))[:10]:
            if not isinstance(item, dict):
                continue
            longitude, latitude = _coordinates(item.get("location"))
            places.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "address": _string(item.get("address")),
                    "type": str(item.get("type") or ""),
                    "city": str(item.get("cityname") or city),
                    "district": str(item.get("adname") or ""),
                    "longitude": longitude,
                    "latitude": latitude,
                    "rating": _nested_string(item, "biz_ext", "rating"),
                    "average_cost": _nested_string(item, "biz_ext", "cost"),
                }
            )
        return {"query": query, "city": city, "places": places}

    async def _route_quote(self, args: dict[str, object]) -> dict[str, object]:
        origin_name = _required_text(args, "origin", 120)
        destination_name = _required_text(args, "destination", 120)
        city = _optional_text(args, "city", 60)
        mode = str(args.get("mode") or "driving")
        if mode not in {"driving", "walking", "transit"}:
            raise ToolInputError("路线方式仅支持 driving、walking 或 transit。")
        origin = await self._geocode(origin_name, city)
        destination = await self._geocode(destination_name, city)
        path = "/v3/direction/transit/integrated" if mode == "transit" else f"/v3/direction/{mode}"
        params = {
            "origin": origin["location"],
            "destination": destination["location"],
            "extensions": "base",
        }
        if mode == "transit":
            if not city:
                raise ToolInputError("公交路线需要城市。")
            params["city"] = city
            params["cityd"] = city
        payload = await self._get(path, params)
        route = cast(dict[str, object], payload.get("route") or {})
        paths = _list(route.get("transits" if mode == "transit" else "paths"))
        first = paths[0] if paths and isinstance(paths[0], dict) else {}
        duration = _int(first.get("duration"))
        distance = _int(first.get("distance"))
        if mode == "transit" and not distance:
            distance = _int(route.get("distance"))
        link = "https://uri.amap.com/navigation?" + urlencode(
            {
                "from": f"{origin['location']},{origin_name}",
                "to": f"{destination['location']},{destination_name}",
                "mode": "car" if mode == "driving" else "walk" if mode == "walking" else "bus",
                "policy": "1",
                "src": "travel_planner_agent",
                "coordinate": "gaode",
                "callnative": "1",
            }
        )
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_meters": distance,
            "duration_minutes": round(duration / 60) if duration is not None else None,
            "tolls_cents": round(float(_string(first.get("tolls")) or 0) * 100),
            "taxi_cost_cents": round(float(_string(route.get("taxi_cost")) or 0) * 100),
            "map_url": link,
        }

    async def _geocode(self, address: str, city: str) -> dict[str, object]:
        payload = await self._get("/v3/geocode/geo", {"address": address, "city": city})
        values = _list(payload.get("geocodes"))
        if not values or not isinstance(values[0], dict):
            raise ToolUnavailableError(f"无法定位: {address}")
        value = values[0]
        longitude, latitude = _coordinates(value.get("location"))
        return {
            "name": address,
            "formatted_address": str(value.get("formatted_address") or address),
            "location": str(value.get("location") or ""),
            "longitude": longitude,
            "latitude": latitude,
        }

    async def _get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        cleaned = {key: value for key, value in params.items() if value not in {None, ""}}
        cleaned["key"] = self._key
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(
                f"https://restapi.amap.com{path}",
                params={key: str(value) for key, value in cleaned.items()},
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("status")) != "1":
            message = (
                str(payload.get("info") or "高德服务返回异常")
                if isinstance(payload, dict)
                else "高德响应无效"
            )
            raise ToolUnavailableError(message)
        return cast(dict[str, object], payload)


class QWeatherProvider:
    name = "qweather"

    def __init__(
        self,
        api_host: str,
        api_key: str,
        timeout: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._host = _https_host(api_host)
        self._key, self._timeout, self._transport = api_key, timeout, transport

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        if operation != "weather_forecast":
            raise ToolInputError("不支持的天气工具。")
        if not self._host or not self._key:
            raise ToolUnavailableError("和风天气 API Host 或 Key 未配置。")
        city = _required_text(args, "city", 80)
        location = await self._get("/geo/v2/city/lookup", {"location": city, "number": "1"})
        candidates = _list(location.get("location"))
        if not candidates or not isinstance(candidates[0], dict):
            raise ToolUnavailableError(f"和风天气无法定位: {city}")
        place = candidates[0]
        forecast = await self._get("/v7/weather/3d", {"location": str(place.get("id") or "")})
        daily = []
        for item in _list(forecast.get("daily"))[:3]:
            if isinstance(item, dict):
                daily.append(
                    {
                        "date": item.get("fxDate"),
                        "text_day": item.get("textDay"),
                        "text_night": item.get("textNight"),
                        "temp_min_c": _int(item.get("tempMin")),
                        "temp_max_c": _int(item.get("tempMax")),
                        "precip_mm": item.get("precip"),
                        "humidity_percent": _int(item.get("humidity")),
                        "wind_day": item.get("windDirDay"),
                    }
                )
        return {
            "city": str(place.get("name") or city),
            "administrative_area": str(place.get("adm1") or ""),
            "forecast": daily,
            "source_url": forecast.get("fxLink"),
            "update_time": forecast.get("updateTime"),
        }

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(
                f"{self._host}{path}", params=params, headers={"X-QW-Api-Key": self._key}
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code")) != "200":
            raise ToolUnavailableError("和风天气服务返回异常。")
        return cast(dict[str, object], payload)


class XiaohongshuMcpProvider:
    name = "xiaohongshu"

    def __init__(
        self,
        endpoint: str,
        timeout: int,
        max_results: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint, self._timeout = endpoint, timeout
        self._max_results, self._transport = max_results, transport

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        if operation == "guide_search_xhs":
            keyword = _required_text(args, "query", 80)
            raw = await self._call("search_feeds", {"keyword": keyword})
            guides = self._normalize_guides(raw)[: self._max_results]
            return {
                "query": keyword,
                "guides": guides,
                "notice": "社区攻略是主观经验, 营业、票价和路线需另行复核。",
            }
        if operation == "guide_detail_xhs":
            feed_id = _required_text(args, "feed_id", 160)
            token = _required_text(args, "xsec_token", 2000)
            load_all_comments = args.get("load_all_comments") is True
            raw = await self._call(
                "get_feed_detail",
                {
                    "feed_id": feed_id,
                    "xsec_token": token,
                    "load_all_comments": load_all_comments,
                },
            )
            return self._normalize_detail(raw, feed_id)
        raise ToolInputError("小红书连接器仅允许只读搜索和详情读取。")

    async def _call(self, tool_name: str, arguments: dict[str, object]) -> object:
        headers = {"Accept": "application/json, text/event-stream"}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            initialized = await client.post(
                self._endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "travel-planner-agent", "version": "0.1.0"},
                    },
                },
            )
            initialized.raise_for_status()
            session_id = initialized.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            await client.post(
                self._endpoint,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            response = await client.post(
                self._endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
            )
            response.raise_for_status()
        envelope = _mcp_envelope(response)
        if isinstance(envelope, dict) and envelope.get("error"):
            raise ToolUnavailableError(str(envelope["error"])[:300])
        result = envelope.get("result") if isinstance(envelope, dict) else None
        if isinstance(result, dict) and result.get("isError"):
            raise ToolUnavailableError("小红书 Worker 未登录、被风控或页面契约已变化。")
        content = result.get("content") if isinstance(result, dict) else []
        for item in _list(content):
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text[:16000]}
        return result or {}

    @staticmethod
    def _normalize_guides(raw: object) -> list[dict[str, object]]:
        candidates: object = raw
        if isinstance(raw, dict):
            for key in ("feeds", "items", "data"):
                if isinstance(raw.get(key), list):
                    candidates = raw[key]
                    break
        values = _list(candidates)
        normalized: list[dict[str, object]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            card = value.get("noteCard") if isinstance(value.get("noteCard"), dict) else value
            assert isinstance(card, dict)
            guide_id = str(value.get("id") or card.get("noteId") or "")
            token = str(value.get("xsecToken") or value.get("xsec_token") or "")
            author_value = card.get("user")
            author: dict[str, object] = author_value if isinstance(author_value, dict) else {}
            normalized.append(
                {
                    "id": guide_id,
                    "xsec_token": token,
                    "title": str(card.get("displayTitle") or card.get("title") or "未命名攻略"),
                    "summary": str(card.get("desc") or card.get("content") or "")[:1200],
                    "author": str(author.get("nickname") or author.get("nickName") or ""),
                    "url": f"https://www.xiaohongshu.com/explore/{guide_id}?xsec_token={token}"
                    if guide_id and token
                    else "https://www.xiaohongshu.com/explore",
                    "source": "xiaohongshu",
                }
            )
        return normalized

    @staticmethod
    def _normalize_detail(raw: object, feed_id: str) -> dict[str, object]:
        root: dict[str, object] = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        data_value = root.get("data")
        data: dict[str, object] = (
            cast(dict[str, object], data_value) if isinstance(data_value, dict) else root
        )
        note_value = data.get("note")
        note: dict[str, object] = (
            cast(dict[str, object], note_value) if isinstance(note_value, dict) else data
        )
        card_value = note.get("noteCard")
        if isinstance(card_value, dict):
            note = cast(dict[str, object], card_value)
        user_value = note.get("user")
        user: dict[str, object] = (
            cast(dict[str, object], user_value) if isinstance(user_value, dict) else {}
        )
        images = _image_urls(note)
        comments_value = data.get("comments") or data.get("commentList") or root.get("comments")
        if isinstance(comments_value, dict):
            comments_value = next(
                (
                    comments_value.get(key)
                    for key in ("list", "items", "comments", "commentList")
                    if isinstance(comments_value.get(key), list)
                ),
                [],
            )
        comments = []
        for item in _list(comments_value)[:10]:
            if not isinstance(item, dict):
                continue
            comment_user_value = item.get("user") or item.get("userInfo")
            comment_user: dict[str, object] = (
                cast(dict[str, object], comment_user_value)
                if isinstance(comment_user_value, dict)
                else {}
            )
            comments.append(
                {
                    "author": str(
                        comment_user.get("nickname") or comment_user.get("nickName") or ""
                    ),
                    "content": str(item.get("content") or item.get("text") or "")[:800],
                    "likes": _int(item.get("likeCount") or item.get("like_count")),
                }
            )
        interactions_value = note.get("interactInfo")
        interactions: dict[str, object] = (
            cast(dict[str, object], interactions_value)
            if isinstance(interactions_value, dict)
            else {}
        )
        return {
            "id": str(note.get("noteId") or note.get("id") or feed_id),
            "title": str(note.get("title") or note.get("displayTitle") or "未命名攻略"),
            "content": str(note.get("desc") or note.get("content") or "")[:24000],
            "author": str(user.get("nickname") or user.get("nickName") or ""),
            "images": images[:30],
            "comments": comments,
            "metadata": {
                "liked_count": _int(interactions.get("likedCount") or note.get("likedCount")),
                "collected_count": _int(
                    interactions.get("collectedCount") or note.get("collectedCount")
                ),
                "comment_count": _int(interactions.get("commentCount") or note.get("commentCount")),
                "share_count": _int(interactions.get("shareCount") or note.get("shareCount")),
                "source_snapshot": "xiaohongshu_mcp",
            },
        }


class GuideLibraryProvider:
    name = "local_guide_library"

    def __init__(self, store_factory: Callable[[], SqlAlchemyToolStore]) -> None:
        self._store_factory = store_factory

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]:
        if operation != "guide_library_search" or not owner_user_id:
            raise ToolInputError("攻略库检索请求无效。")
        query = _required_text(args, "query", 120)
        city = _optional_text(args, "city", 100)
        terms = [value.casefold() for value in query.split() if value]
        async with self._store_factory() as store:
            guides = await store.list_guides(owner_user_id, 100, library_only=True)
        matches = []
        for guide in guides:
            haystack = " ".join(
                (guide.title, guide.city, guide.summary, guide.content, guide.user_notes)
            ).casefold()
            if city and city.casefold() != guide.city.casefold():
                continue
            if terms and not all(term in haystack for term in terms):
                continue
            matches.append(
                {
                    "guide_id": guide.id,
                    "title": guide.title,
                    "city": guide.city,
                    "author": guide.author,
                    "content": (guide.content or guide.summary)[:6000],
                    "user_notes": guide.user_notes[:2000],
                    "source_url": guide.url,
                    "detail_fetched_at": guide.detail_fetched_at.isoformat()
                    if guide.detail_fetched_at
                    else None,
                    "stale": bool(
                        guide.detail_expires_at and guide.detail_expires_at <= datetime.now(UTC)
                    ),
                }
            )
            if len(matches) == 8:
                break
        return {"query": query, "city": city, "guides": matches, "source": "private_library"}


def _mcp_envelope(response: httpx.Response) -> object:
    if "text/event-stream" in response.headers.get("content-type", ""):
        for line in reversed(response.text.splitlines()):
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise ToolUnavailableError("MCP 响应缺少 data 事件。")
    return response.json()


def _https_host(value: str) -> str:
    if not value:
        return ""
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("QWEATHER_API_HOST must be an HTTPS host")
    return f"https://{parsed.netloc}"


def _required_text(args: dict[str, object], key: str, maximum: int) -> str:
    value = str(args.get(key) or "").strip()
    if not value or len(value) > maximum:
        raise ToolInputError(f"{key} 必须包含 1 至 {maximum} 个字符。")
    return value


def _optional_text(args: dict[str, object], key: str, maximum: int) -> str:
    value = str(args.get(key) or "").strip()
    if len(value) > maximum:
        raise ToolInputError(f"{key} 不能超过 {maximum} 个字符。")
    return value


def _coordinates(value: object) -> tuple[float | None, float | None]:
    parts = str(value or "").split(",")
    try:
        return float(parts[0]), float(parts[1])
    except (IndexError, ValueError):
        return None, None


def _image_urls(note: dict[str, object]) -> list[str]:
    values = note.get("imageList") or note.get("images") or note.get("image_list")
    result: list[str] = []
    for item in _list(values):
        if isinstance(item, str) and item.startswith("http"):
            result.append(item)
            continue
        if not isinstance(item, dict):
            continue
        candidate = item.get("urlDefault") or item.get("urlPre") or item.get("url")
        if isinstance(candidate, str) and candidate.startswith("http"):
            result.append(candidate)
            continue
        info_value = item.get("infoList")
        info: list[object] = cast(list[object], info_value) if isinstance(info_value, list) else []
        for value in info:
            if isinstance(value, dict) and str(value.get("url") or "").startswith("http"):
                result.append(str(value["url"]))
                break
    return list(dict.fromkeys(result))


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value or "")


def _int(value: object) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _nested_string(value: dict[str, object], parent: str, child: str) -> str:
    nested = value.get(parent)
    return _string(nested.get(child)) if isinstance(nested, dict) else ""
