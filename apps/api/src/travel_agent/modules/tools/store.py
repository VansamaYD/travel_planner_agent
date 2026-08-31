from __future__ import annotations

import json
import re
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
    ) -> dict[str, str]:
        identities: dict[str, str] = {}
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
                "token": str(guide.get("xsec_token") or "")[:2000],
                "source_query": str(guide.get("source_query") or "")[:300],
            }
            inferred_city = _city_hint(
                " ".join((values["source_query"], values["title"], values["summary"]))
            )
            city = str(guide.get("city") or inferred_city)[:100]
            if row is None:
                row_id = new_uuid7()
                self.session.add(
                    GuideCandidateRow(
                        id=row_id,
                        owner_user_id=owner_user_id,
                        provider=provider,
                        external_id_hash=external_hash,
                        external_id_ciphertext=self._encrypt(external_id, "guide.external_id"),
                        access_token_ciphertext=self._optional(values["token"], "guide.token"),
                        source_query_ciphertext=self._optional(
                            values["source_query"], "guide.source_query"
                        ),
                        city_ciphertext=self._optional(city, "guide.city"),
                        title_ciphertext=self._encrypt(values["title"], "guide.title"),
                        url_ciphertext=self._optional(values["url"], "guide.url"),
                        author_ciphertext=self._optional(values["author"], "guide.author"),
                        summary_ciphertext=self._encrypt(values["summary"], "guide.summary"),
                        content_ciphertext=None,
                        images_ciphertext=None,
                        comments_ciphertext=None,
                        tags_ciphertext=None,
                        metadata_ciphertext=None,
                        user_notes_ciphertext=None,
                        status="discovered",
                        pinned=False,
                        published_at=None,
                        fetched_at=fetched_at,
                        expires_at=expires_at,
                        detail_fetched_at=None,
                        detail_expires_at=None,
                        updated_at=fetched_at,
                    )
                )
                identities[external_id] = row_id
            else:
                identities[external_id] = row.id
                row.external_id_ciphertext = self._encrypt(external_id, "guide.external_id")
                row.access_token_ciphertext = self._optional(values["token"], "guide.token")
                row.source_query_ciphertext = self._optional(
                    values["source_query"], "guide.source_query"
                )
                current_city = self._decrypt(row.city_ciphertext, "guide.city")
                if city and current_city in ("", "未分类"):
                    row.city_ciphertext = self._encrypt(city, "guide.city")
                row.title_ciphertext = self._encrypt(values["title"], "guide.title")
                row.url_ciphertext = self._optional(values["url"], "guide.url")
                row.author_ciphertext = self._optional(values["author"], "guide.author")
                row.summary_ciphertext = self._encrypt(values["summary"], "guide.summary")
                row.fetched_at = fetched_at
                row.expires_at = expires_at
                row.updated_at = fetched_at
        return identities

    async def get_guide(self, owner_user_id: str, guide_id: str) -> GuideCandidate | None:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        return self._guide(row) if row else None

    async def guide_credentials(self, owner_user_id: str, guide_id: str) -> tuple[str, str] | None:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        if row is None or row.external_id_ciphertext is None:
            return None
        return (
            self._protector.decrypt(row.external_id_ciphertext, context="guide.external_id"),
            self._protector.decrypt(row.access_token_ciphertext, context="guide.token")
            if row.access_token_ciphertext
            else "",
        )

    async def set_guide_status(
        self, owner_user_id: str, guide_id: str, status: str, updated_at: datetime
    ) -> bool:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        if row is None:
            return False
        row.status, row.updated_at = status, updated_at
        return True

    async def save_guide_detail(
        self,
        owner_user_id: str,
        guide_id: str,
        detail: dict[str, object],
        fetched_at: datetime,
        expires_at: datetime,
    ) -> GuideCandidate | None:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        if row is None:
            return None
        title = str(detail.get("title") or "").strip()
        author = str(detail.get("author") or "").strip()
        content, tags = _extract_topics(str(detail.get("content") or ""))
        content = content[:24000]
        if title:
            row.title_ciphertext = self._encrypt(title[:300], "guide.title")
        if author:
            row.author_ciphertext = self._encrypt(author[:200], "guide.author")
        row.content_ciphertext = self._optional(content, "guide.content")
        row.summary_ciphertext = self._encrypt(
            (content or self._decrypt(row.summary_ciphertext, "guide.summary"))[:2000],
            "guide.summary",
        )
        images = detail.get("images")
        comments = detail.get("comments")
        if images:
            row.images_ciphertext = self._json_optional(images, "guide.images")
        if comments:
            row.comments_ciphertext = self._json_optional(comments, "guide.comments")
        if tags:
            row.tags_ciphertext = self._json_optional(tags, "guide.tags")
        row.metadata_ciphertext = self._json_optional(detail.get("metadata"), "guide.metadata")
        current_city = self._decrypt(row.city_ciphertext, "guide.city")
        if current_city in ("", "未分类"):
            inferred_city = _city_hint(
                " ".join(
                    (
                        self._decrypt(row.source_query_ciphertext, "guide.source_query"),
                        title,
                        content,
                        " ".join(tags),
                    )
                )
            )
            if inferred_city != "未分类":
                row.city_ciphertext = self._encrypt(inferred_city, "guide.city")
        row.status = "ready"
        row.detail_fetched_at = fetched_at
        row.detail_expires_at = expires_at
        row.updated_at = fetched_at
        await self.session.flush()
        return self._guide(row)

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
    ) -> GuideCandidate | None:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        if row is None:
            return None
        if title is not None:
            row.title_ciphertext = self._encrypt(title[:300], "guide.title")
        if city is not None:
            row.city_ciphertext = self._optional(city[:100], "guide.city")
        if content is not None:
            clean_content, tags = _extract_topics(content)
            row.content_ciphertext = self._optional(clean_content[:24000], "guide.content")
            row.tags_ciphertext = self._json_optional(tags, "guide.tags")
        if user_notes is not None:
            row.user_notes_ciphertext = self._optional(user_notes[:8000], "guide.user_notes")
        if pinned is not None:
            row.pinned = pinned
        row.updated_at = updated_at
        await self.session.flush()
        return self._guide(row)

    async def delete_guide(self, owner_user_id: str, guide_id: str) -> bool:
        row = await self.session.scalar(
            select(GuideCandidateRow).where(
                GuideCandidateRow.id == guide_id,
                GuideCandidateRow.owner_user_id == owner_user_id,
            )
        )
        if row is None:
            return False
        await self.session.delete(row)
        return True

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

    async def list_guides(
        self, owner_user_id: str, limit: int = 50, library_only: bool = False
    ) -> tuple[GuideCandidate, ...]:
        statement = select(GuideCandidateRow).where(
            GuideCandidateRow.owner_user_id == owner_user_id
        )
        if library_only:
            statement = statement.where(GuideCandidateRow.status != "discovered")
        rows = await self.session.scalars(
            statement.order_by(
                GuideCandidateRow.pinned.desc(),
                GuideCandidateRow.updated_at.desc(),
                GuideCandidateRow.fetched_at.desc(),
            ).limit(limit)
        )
        return tuple(self._guide(row) for row in rows)

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

    def _decrypt(self, value: bytes | None, context: str) -> str:
        return self._protector.decrypt(value, context=context) if value else ""

    def _json_optional(self, value: object, context: str) -> bytes | None:
        if value in (None, [], {}):
            return None
        return self._encrypt(json.dumps(value, ensure_ascii=False), context)

    def _json(self, value: bytes | None, context: str, fallback: object) -> object:
        if value is None:
            return fallback
        try:
            return json.loads(self._decrypt(value, context))
        except json.JSONDecodeError:
            return fallback

    def _guide(self, row: GuideCandidateRow) -> GuideCandidate:
        images = self._json(row.images_ciphertext, "guide.images", [])
        comments = self._json(row.comments_ciphertext, "guide.comments", [])
        tags = self._json(row.tags_ciphertext, "guide.tags", [])
        metadata = self._json(row.metadata_ciphertext, "guide.metadata", {})
        return GuideCandidate(
            id=row.id,
            provider=row.provider,
            title=self._decrypt(row.title_ciphertext, "guide.title"),
            url=self._decrypt(row.url_ciphertext, "guide.url"),
            author=self._decrypt(row.author_ciphertext, "guide.author"),
            summary=self._decrypt(row.summary_ciphertext, "guide.summary"),
            city=self._decrypt(row.city_ciphertext, "guide.city"),
            source_query=self._decrypt(row.source_query_ciphertext, "guide.source_query"),
            status=row.status,
            pinned=row.pinned,
            content=self._decrypt(row.content_ciphertext, "guide.content"),
            images=tuple(str(item) for item in images) if isinstance(images, list) else (),
            comments=tuple(item for item in comments if isinstance(item, dict))
            if isinstance(comments, list)
            else (),
            tags=tuple(str(item) for item in tags) if isinstance(tags, list) else (),
            metadata=metadata if isinstance(metadata, dict) else {},
            user_notes=self._decrypt(row.user_notes_ciphertext, "guide.user_notes"),
            fetched_at=_aware(row.fetched_at),
            expires_at=_aware(row.expires_at),
            detail_fetched_at=_aware(row.detail_fetched_at) if row.detail_fetched_at else None,
            detail_expires_at=_aware(row.detail_expires_at) if row.detail_expires_at else None,
        )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _city_hint(query: str) -> str:
    normalized = re.sub(r"\s+", "", query)
    destinations = (
        "北京",
        "上海",
        "天津",
        "重庆",
        "广州",
        "深圳",
        "杭州",
        "苏州",
        "南京",
        "青岛",
        "成都",
        "西安",
        "武汉",
        "长沙",
        "厦门",
        "福州",
        "泉州",
        "大连",
        "沈阳",
        "哈尔滨",
        "长春",
        "济南",
        "烟台",
        "威海",
        "郑州",
        "洛阳",
        "开封",
        "合肥",
        "南昌",
        "贵阳",
        "昆明",
        "大理",
        "丽江",
        "拉萨",
        "三亚",
        "海口",
        "桂林",
        "南宁",
        "珠海",
        "佛山",
        "东莞",
        "汕头",
        "惠州",
        "宁波",
        "温州",
        "绍兴",
        "嘉兴",
        "无锡",
        "扬州",
        "镇江",
        "泰安",
        "淄博",
        "潍坊",
        "日照",
        "秦皇岛",
        "石家庄",
        "太原",
        "呼和浩特",
        "银川",
        "兰州",
        "西宁",
        "乌鲁木齐",
        "喀什",
        "张家界",
        "宜昌",
        "九江",
        "景德镇",
        "黄山",
        "舟山",
        "北海",
        "西双版纳",
        "香格里拉",
        "阿坝",
        "甘孜",
        "延边",
        "漠河",
        "香港",
        "澳门",
        "台北",
        "高雄",
    )
    for destination in destinations:
        if destination in normalized:
            return destination
    match = re.search(r"([\u4e00-\u9fff]{2,8})市(?:旅游|旅行|攻略|景点|美食|酒店)?", normalized)
    return match.group(1) if match else "未分类"


_TOPIC_PATTERN = re.compile(r"#\s*([^#\[\]\n]{1,40}?)\s*\[话题\]\s*#?")


def _extract_topics(content: str) -> tuple[str, list[str]]:
    tags: list[str] = []
    for value in _TOPIC_PATTERN.findall(content):
        tag = " ".join(value.split()).strip("# ")
        if tag and tag not in tags:
            tags.append(tag)
    cleaned = _TOPIC_PATTERN.sub("", content)
    cleaned = re.sub(r"(?:\s*#\s*)+$", "", cleaned).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, tags[:50]
