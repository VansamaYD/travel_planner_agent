from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol

from travel_agent.modules.tools.domain import (
    CacheRecord,
    GuideCandidate,
    ToolDescriptor,
    ToolError,
    ToolInputError,
    ToolResult,
    ToolUnavailableError,
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class ToolProvider(Protocol):
    name: str

    async def execute(
        self, operation: str, args: dict[str, object], owner_user_id: str = ""
    ) -> dict[str, object]: ...


class ToolStore(Protocol):
    async def get_cache(self, key_hash: str, accessed_at: datetime) -> CacheRecord | None: ...
    async def put_cache(
        self,
        *,
        key_hash: str,
        provider: str,
        operation: str,
        scope_hash: str,
        payload: dict[str, object],
        queried_at: datetime,
        expires_at: datetime,
        stale_until: datetime,
    ) -> None: ...
    async def record_usage(
        self,
        *,
        owner_user_id: str,
        provider: str,
        operation: str,
        query_hash: str,
        cache_status: str,
        status: str,
        duration_ms: int,
        result_count: int,
        error_code: str | None,
        created_at: datetime,
    ) -> None: ...
    async def upsert_guides(
        self,
        owner_user_id: str,
        provider: str,
        guides: list[dict[str, object]],
        fetched_at: datetime,
        expires_at: datetime,
    ) -> dict[str, str]: ...
    async def purge_expired(self, before: datetime, limit: int = 100) -> int: ...
    async def list_guides(
        self, owner_user_id: str, limit: int = 50, library_only: bool = False
    ) -> tuple[GuideCandidate, ...]: ...
    async def get_guide(self, owner_user_id: str, guide_id: str) -> GuideCandidate | None: ...
    async def guide_credentials(
        self, owner_user_id: str, guide_id: str
    ) -> tuple[str, str] | None: ...
    async def set_guide_status(
        self, owner_user_id: str, guide_id: str, status: str, updated_at: datetime
    ) -> bool: ...
    async def save_guide_detail(
        self,
        owner_user_id: str,
        guide_id: str,
        detail: dict[str, object],
        fetched_at: datetime,
        expires_at: datetime,
    ) -> GuideCandidate | None: ...
    async def update_guide(
        self,
        owner_user_id: str,
        guide_id: str,
        *,
        title: str | None,
        city: str | None,
        content: str | None,
        user_notes: str | None,
        pinned: bool | None,
        updated_at: datetime,
    ) -> GuideCandidate | None: ...
    async def delete_guide(self, owner_user_id: str, guide_id: str) -> bool: ...
    async def usage_summary(
        self, owner_user_id: str, since: datetime
    ) -> tuple[dict[str, object], ...]: ...
    async def commit(self) -> None: ...
    def key_hash(self, canonical: str) -> str: ...
    def scope_hash(self, scope: str) -> str: ...
    async def __aenter__(self) -> ToolStore: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    descriptor: ToolDescriptor
    provider: ToolProvider
    label: str
    private_scope: bool = False
    expose_to_model: bool = True


class ToolGateway:
    def __init__(
        self,
        store_factory: Callable[[], ToolStore],
        clock: Clock,
        tools: tuple[RegisteredTool, ...],
    ) -> None:
        self._store_factory, self._clock = store_factory, clock
        self._tools = {tool.descriptor.name: tool for tool in tools}
        self._locks: dict[str, asyncio.Lock] = {}
        self._failures: dict[str, tuple[int, datetime]] = {}

    def model_descriptors(self) -> tuple[dict[str, object], ...]:
        return tuple(
            tool.descriptor.model_schema() for tool in self._tools.values() if tool.expose_to_model
        )

    def capabilities(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "name": tool.descriptor.name,
                "provider": tool.descriptor.provider,
                "ttl_seconds": tool.descriptor.ttl_seconds,
                "stale_seconds": tool.descriptor.stale_seconds,
                "private_scope": tool.private_scope,
            }
            for tool in self._tools.values()
        )

    def label(self, name: str) -> str:
        tool = self._tools.get(name)
        return tool.label if tool else name

    async def list_guides(
        self, owner_user_id: str, limit: int = 50, library_only: bool = False
    ) -> tuple[GuideCandidate, ...]:
        async with self._store_factory() as store:
            return await store.list_guides(owner_user_id, limit, library_only)

    async def get_guide(self, owner_user_id: str, guide_id: str) -> GuideCandidate | None:
        async with self._store_factory() as store:
            return await store.get_guide(owner_user_id, guide_id)

    async def update_guide(
        self,
        owner_user_id: str,
        guide_id: str,
        *,
        title: str | None = None,
        city: str | None = None,
        content: str | None = None,
        user_notes: str | None = None,
        pinned: bool | None = None,
    ) -> GuideCandidate | None:
        async with self._store_factory() as store:
            value = await store.update_guide(
                owner_user_id,
                guide_id,
                title=title,
                city=city,
                content=content,
                user_notes=user_notes,
                pinned=pinned,
                updated_at=self._clock.now(),
            )
            await store.commit()
            return value

    async def delete_guide(self, owner_user_id: str, guide_id: str) -> bool:
        async with self._store_factory() as store:
            deleted = await store.delete_guide(owner_user_id, guide_id)
            await store.commit()
            return deleted

    async def import_guide(self, owner_user_id: str, guide_id: str) -> GuideCandidate:
        async with self._store_factory() as store:
            credentials = await store.guide_credentials(owner_user_id, guide_id)
            if credentials is None:
                raise ToolInputError("攻略候选不存在。")
            await store.set_guide_status(owner_user_id, guide_id, "downloading", self._clock.now())
            await store.commit()
        feed_id, token = credentials
        if not token:
            await self._mark_guide_failed(owner_user_id, guide_id)
            raise ToolInputError("搜索结果缺少详情访问令牌, 请重新搜索后再保存。")
        try:
            result = await self.execute(
                "guide_detail_xhs",
                {"feed_id": feed_id, "xsec_token": token},
                owner_user_id,
            )
            async with self._store_factory() as store:
                value = await store.save_guide_detail(
                    owner_user_id,
                    guide_id,
                    result.data,
                    result.queried_at,
                    result.expires_at,
                )
                await store.commit()
            if value is None:
                raise ToolInputError("攻略候选不存在。")
            return value
        except Exception:
            await self._mark_guide_failed(owner_user_id, guide_id)
            raise

    async def _mark_guide_failed(self, owner_user_id: str, guide_id: str) -> None:
        async with self._store_factory() as store:
            await store.set_guide_status(owner_user_id, guide_id, "failed", self._clock.now())
            await store.commit()

    def now(self) -> datetime:
        return self._clock.now()

    async def usage_summary(
        self, owner_user_id: str, since: datetime
    ) -> tuple[dict[str, object], ...]:
        async with self._store_factory() as store:
            return await store.usage_summary(owner_user_id, since)

    async def execute(self, name: str, args: dict[str, object], owner_user_id: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolInputError("模型请求了未授权的工具。")
        normalized = _normalize(args)
        scope = owner_user_id if tool.private_scope else "public"
        canonical = json.dumps(
            [tool.descriptor.provider, name, scope, normalized],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        async with self._store_factory() as store:
            key_hash = store.key_hash(canonical)
            scope_hash = store.scope_hash(scope)
            cached = await store.get_cache(key_hash, self._clock.now())
            if cached is not None and cached.expires_at > self._clock.now():
                result = self._cached_result(tool, cached, "hit")
                await self._usage(store, owner_user_id, tool, key_hash, "hit", "ok", result)
                await store.commit()
                return result

        lock = self._locks.setdefault(key_hash, asyncio.Lock())
        async with lock:
            try:
                return await self._fetch(
                    tool, normalized, owner_user_id, key_hash, scope_hash, cached
                )
            finally:
                self._locks.pop(key_hash, None)

    async def _fetch(
        self,
        tool: RegisteredTool,
        args: dict[str, object],
        owner_user_id: str,
        key_hash: str,
        scope_hash: str,
        stale: CacheRecord | None,
    ) -> ToolResult:
        async with self._store_factory() as store:
            second = await store.get_cache(key_hash, self._clock.now())
            if second is not None and second.expires_at > self._clock.now():
                result = self._cached_result(tool, second, "hit")
                await self._usage(store, owner_user_id, tool, key_hash, "hit", "ok", result)
                await store.commit()
                return result
        started = time.perf_counter()
        try:
            self._check_circuit(tool)
            data = await tool.provider.execute(tool.descriptor.name, args, owner_user_id)
            now = self._clock.now()
            expires_at = now + timedelta(seconds=tool.descriptor.ttl_seconds)
            stale_until = expires_at + timedelta(seconds=tool.descriptor.stale_seconds)
            async with self._store_factory() as store:
                if tool.descriptor.name == "guide_search_xhs":
                    guides = data.get("guides")
                    if isinstance(guides, list):
                        query = str(data.get("query") or "")
                        normalized_guides = [item for item in guides if isinstance(item, dict)]
                        for guide in normalized_guides:
                            guide["source_query"] = query
                        identities = await store.upsert_guides(
                            owner_user_id,
                            tool.provider.name,
                            normalized_guides,
                            now,
                            expires_at,
                        )
                        for guide in normalized_guides:
                            external_id = str(guide.get("id") or guide.get("url") or "")
                            if external_id in identities:
                                guide["candidate_id"] = identities[external_id]
                                guide["status"] = "discovered"
                await store.put_cache(
                    key_hash=key_hash,
                    provider=tool.provider.name,
                    operation=tool.descriptor.name,
                    scope_hash=scope_hash,
                    payload=data,
                    queried_at=now,
                    expires_at=expires_at,
                    stale_until=stale_until,
                )
                result = ToolResult(
                    data, tool.provider.name, tool.descriptor.name, now, expires_at, "miss"
                )
                await self._usage(
                    store,
                    owner_user_id,
                    tool,
                    key_hash,
                    "miss",
                    "ok",
                    result,
                    int((time.perf_counter() - started) * 1000),
                )
                await store.purge_expired(now)
                await store.commit()
            self._failures.pop(tool.descriptor.name, None)
            return result
        except Exception as error:
            if not isinstance(error, ToolInputError):
                self._record_failure(tool)
            now = self._clock.now()
            fallback = stale
            if fallback is not None and fallback.stale_until > now:
                result = self._cached_result(
                    tool,
                    fallback,
                    "stale",
                    ("上游查询失败, 已返回过期缓存; 请核对关键信息。",),
                )
                async with self._store_factory() as store:
                    await self._usage(
                        store,
                        owner_user_id,
                        tool,
                        key_hash,
                        "stale",
                        "degraded",
                        result,
                        int((time.perf_counter() - started) * 1000),
                        getattr(error, "code", "provider_error"),
                    )
                    await store.commit()
                return result
            async with self._store_factory() as store:
                await store.record_usage(
                    owner_user_id=owner_user_id,
                    provider=tool.provider.name,
                    operation=tool.descriptor.name,
                    query_hash=key_hash,
                    cache_status="miss",
                    status="failed",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    result_count=0,
                    error_code=getattr(error, "code", "provider_error"),
                    created_at=now,
                )
                await store.commit()
            if isinstance(error, ToolError):
                raise
            raise ToolUnavailableError("外部数据源暂时不可用。") from error

    async def _usage(
        self,
        store: ToolStore,
        owner_user_id: str,
        tool: RegisteredTool,
        key_hash: str,
        cache_status: str,
        status: str,
        result: ToolResult,
        duration_ms: int = 0,
        error_code: str | None = None,
    ) -> None:
        await store.record_usage(
            owner_user_id=owner_user_id,
            provider=tool.provider.name,
            operation=tool.descriptor.name,
            query_hash=key_hash,
            cache_status=cache_status,
            status=status,
            duration_ms=duration_ms,
            result_count=_result_count(result.data),
            error_code=error_code,
            created_at=self._clock.now(),
        )

    @staticmethod
    def _cached_result(
        tool: RegisteredTool,
        cached: CacheRecord,
        status: str,
        warnings: tuple[str, ...] = (),
    ) -> ToolResult:
        return ToolResult(
            cached.payload,
            tool.provider.name,
            tool.descriptor.name,
            cached.queried_at,
            cached.expires_at,
            status,
            warnings,
        )

    def _check_circuit(self, tool: RegisteredTool) -> None:
        state = self._failures.get(tool.descriptor.name)
        if state is not None and state[0] >= 3 and state[1] > self._clock.now():
            raise ToolUnavailableError("该外部数据源连续失败, 已短暂熔断。")

    def _record_failure(self, tool: RegisteredTool) -> None:
        count, _ = self._failures.get(tool.descriptor.name, (0, self._clock.now()))
        self._failures[tool.descriptor.name] = (
            count + 1,
            self._clock.now() + timedelta(seconds=60),
        )


def _normalize(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ToolInputError("工具参数必须是对象。")
    normalized: dict[str, object] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, str):
            normalized[str(key)] = " ".join(item.split())
        elif isinstance(item, (int, float, bool)) or item is None:
            normalized[str(key)] = item
        else:
            raise ToolInputError("工具参数包含不支持的结构。")
    return normalized


def _result_count(data: dict[str, object]) -> int:
    for key in ("places", "forecast", "guides"):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    return 1 if data else 0
