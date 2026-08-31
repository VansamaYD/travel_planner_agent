from __future__ import annotations

import json
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.tools.domain import CacheRecord, GuideCandidate
from travel_agent.modules.tools.models import ExternalCacheRow, ExternalUsageRow, GuideCandidateRow
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, value: str, *, context: str) -> bytes: ...
    def decrypt(self, payload: bytes, *, context: str) -> str: ...
    def digest(self, value: str, *, context: str) -> str: ...


class SqlAlchemyToolStore:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], protector: TextProtector
    ) -> None:
        self._factory, self._protector = session_factory, protector
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc_type is not None:
                await self._session.rollback()
            await self._session.close()
        self._session = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Tool store inactive")
        return self._session

    async def get_cache(self, key_hash: str, accessed_at: datetime) -> CacheRecord | None:
        row = await self.session.get(ExternalCacheRow, key_hash)
        if row is None:
            return None
        row.last_accessed_at = accessed_at
        row.hit_count += 1
        payload = json.loads(
            self._protector.decrypt(row.payload_ciphertext, context="external.cache.payload")
        )
        return CacheRecord(
            row.key_hash,
            payload,
            _aware(row.queried_at),
            _aware(row.expires_at),
            _aware(row.stale_until),
        )

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
    ) -> None:
        row = await self.session.get(ExternalCacheRow, key_hash)
        ciphertext = self._protector.encrypt(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            context="external.cache.payload",
        )
        if row is None:
            self.session.add(
                ExternalCacheRow(
                    key_hash=key_hash,
                    provider=provider,
                    operation=operation,
                    scope_hash=scope_hash,
                    payload_ciphertext=ciphertext,
                    queried_at=queried_at,
                    expires_at=expires_at,
                    stale_until=stale_until,
                    last_accessed_at=queried_at,
                    hit_count=0,
                )
            )
            return
        row.payload_ciphertext = ciphertext
        row.queried_at = queried_at
        row.expires_at = expires_at
        row.stale_until = stale_until
        row.last_accessed_at = queried_at

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
    ) -> None:
        self.session.add(
            ExternalUsageRow(
                id=new_uuid7(),
                owner_user_id=owner_user_id,
                provider=provider,
                operation=operation,
                query_hash=query_hash,
                cache_status=cache_status,
                status=status,
                duration_ms=duration_ms,
                result_count=result_count,
                error_code=error_code,
                created_at=created_at,
            )
        )

    async def upsert_guides(
        self,
        owner_user_id: str,
        provider: str,
        guides: list[dict[str, object]],
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None:
        for guide in guides[:10]:
            external_id = str(guide.get("id") or guide.get("url") or guide.get("title") or "")
            if not external_id:
                continue
            external_hash = self._protector.digest(
                external_id, context=f"guide.external.{owner_user_id}.{provider}"
            )
            row = await self.session.scalar(
                select(GuideCandidateRow).where(
                    GuideCandidateRow.owner_user_id == owner_user_id,
                    GuideCandidateRow.provider == provider,
                    GuideCandidateRow.external_id_hash == external_hash,
                )
            )
            values = {
                "title": str(guide.get("title") or "未命名攻略")[:300],
                "url": str(guide.get("url") or "")[:2000],
                "author": str(guide.get("author") or "")[:200],
                "summary": str(guide.get("summary") or guide.get("content") or "")[:2000],
            }
            if row is None:
                self.session.add(
                    GuideCandidateRow(
                        id=new_uuid7(),
                        owner_user_id=owner_user_id,
                        provider=provider,
                        external_id_hash=external_hash,
                        title_ciphertext=self._encrypt(values["title"], "guide.title"),
                        url_ciphertext=self._optional(values["url"], "guide.url"),
                        author_ciphertext=self._optional(values["author"], "guide.author"),
                        summary_ciphertext=self._encrypt(values["summary"], "guide.summary"),
                        published_at=None,
                        fetched_at=fetched_at,
                        expires_at=expires_at,
                    )
                )
            else:
                row.title_ciphertext = self._encrypt(values["title"], "guide.title")
                row.url_ciphertext = self._optional(values["url"], "guide.url")
                row.author_ciphertext = self._optional(values["author"], "guide.author")
                row.summary_ciphertext = self._encrypt(values["summary"], "guide.summary")
                row.fetched_at = fetched_at
                row.expires_at = expires_at

    async def commit(self) -> None:
        await self.session.commit()

    async def purge_expired(self, before: datetime, limit: int = 100) -> int:
        keys = tuple(
            await self.session.scalars(
                select(ExternalCacheRow.key_hash)
                .where(ExternalCacheRow.stale_until < before)
                .limit(limit)
            )
        )
        if keys:
            await self.session.execute(
                delete(ExternalCacheRow).where(ExternalCacheRow.key_hash.in_(keys))
            )
        return len(keys)

    async def list_guides(self, owner_user_id: str, limit: int = 50) -> tuple[GuideCandidate, ...]:
        rows = await self.session.scalars(
            select(GuideCandidateRow)
            .where(GuideCandidateRow.owner_user_id == owner_user_id)
            .order_by(GuideCandidateRow.fetched_at.desc())
            .limit(limit)
        )
        return tuple(
            GuideCandidate(
                id=row.id,
                provider=row.provider,
                title=self._protector.decrypt(row.title_ciphertext, context="guide.title"),
                url=self._protector.decrypt(row.url_ciphertext, context="guide.url")
                if row.url_ciphertext
                else "",
                author=self._protector.decrypt(row.author_ciphertext, context="guide.author")
                if row.author_ciphertext
                else "",
                summary=self._protector.decrypt(row.summary_ciphertext, context="guide.summary"),
                fetched_at=_aware(row.fetched_at),
                expires_at=_aware(row.expires_at),
            )
            for row in rows
        )

    async def usage_summary(
        self, owner_user_id: str, since: datetime
    ) -> tuple[dict[str, object], ...]:
        rows = await self.session.execute(
            select(
                ExternalUsageRow.provider,
                ExternalUsageRow.operation,
                ExternalUsageRow.cache_status,
                ExternalUsageRow.status,
                func.count(ExternalUsageRow.id),
                func.sum(ExternalUsageRow.duration_ms),
                func.sum(ExternalUsageRow.result_count),
            )
            .where(
                ExternalUsageRow.owner_user_id == owner_user_id,
                ExternalUsageRow.created_at >= since,
            )
            .group_by(
                ExternalUsageRow.provider,
                ExternalUsageRow.operation,
                ExternalUsageRow.cache_status,
                ExternalUsageRow.status,
            )
            .order_by(ExternalUsageRow.provider, ExternalUsageRow.operation)
        )
        return tuple(
            {
                "provider": row[0],
                "operation": row[1],
                "cache_status": row[2],
                "status": row[3],
                "calls": int(row[4] or 0),
                "duration_ms": int(row[5] or 0),
                "result_count": int(row[6] or 0),
            }
            for row in rows
        )

    def key_hash(self, canonical: str) -> str:
        return self._protector.digest(canonical, context="external.cache.key")

    def scope_hash(self, scope: str) -> str:
        return self._protector.digest(scope, context="external.cache.scope")

    def _encrypt(self, value: str, context: str) -> bytes:
        return self._protector.encrypt(value, context=context)

    def _optional(self, value: str, context: str) -> bytes | None:
        return self._encrypt(value, context) if value else None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
