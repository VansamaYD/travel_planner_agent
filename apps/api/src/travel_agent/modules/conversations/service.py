from __future__ import annotations

import json
import re
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol

from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.conversations.domain import (
    AgentRun,
    ChatMessage,
    Conversation,
    ModelStreamEvent,
)
from travel_agent.modules.tools.domain import ToolError, ToolResult
from travel_agent.shared.domain.ids import new_uuid7


class ConversationError(Exception):
    code = "conversation_error"


class ConversationNotFoundError(ConversationError):
    code = "conversation_not_found"


class ConversationPermissionError(ConversationError):
    code = "conversation_permission_denied"


class ChatProvider(Protocol):
    def stream_turn(
        self,
        messages: tuple[dict[str, object], ...],
        tools: tuple[dict[str, object], ...],
    ) -> AsyncIterator[ModelStreamEvent]: ...


class ToolRuntime(Protocol):
    def model_descriptors(self) -> tuple[dict[str, object], ...]: ...
    def label(self, name: str) -> str: ...
    async def execute(
        self, name: str, args: dict[str, object], owner_user_id: str
    ) -> ToolResult: ...


class KnowledgeRuntime(Protocol):
    async def capture_place_results(
        self, owner_user_id: str, data: dict[str, object], reason: str = "map_refresh"
    ) -> tuple[object, ...]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class ConversationStore(Protocol):
    async def create(self, value: Conversation) -> None: ...
    async def list_for(self, user_id: str) -> tuple[Conversation, ...]: ...
    async def get(self, conversation_id: str) -> Conversation | None: ...
    async def messages(self, conversation_id: str) -> tuple[ChatMessage, ...]: ...
    async def start(self, message: ChatMessage, run: AgentRun) -> None: ...
    async def event(
        self,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None: ...
    async def complete(
        self,
        run_id: str,
        message: ChatMessage,
        completed_at: datetime,
        artifacts: tuple[dict[str, object], ...] = (),
    ) -> None: ...
    async def fail(self, run_id: str, completed_at: datetime) -> None: ...
    async def rename(self, conversation_id: str, title: str, updated_at: datetime) -> None: ...
    async def delete(self, conversation_id: str) -> bool: ...
    async def commit(self) -> None: ...
    async def __aenter__(self) -> ConversationStore: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class ConversationService:
    def __init__(
        self,
        store_factory: Callable[[], ConversationStore],
        provider: ChatProvider,
        tool_runtime: ToolRuntime,
        knowledge_runtime: KnowledgeRuntime,
        clock: Clock,
    ) -> None:
        self._store_factory = store_factory
        self._provider, self._tools = provider, tool_runtime
        self._knowledge, self._clock = knowledge_runtime, clock

    async def create(self, session: AuthenticatedSession, csrf: str | None) -> Conversation:
        self._csrf(session, csrf)
        now = self._clock.now()
        value = Conversation(new_uuid7(), session.user.id, "新对话", now, now)
        async with self._store_factory() as store:
            await store.create(value)
            await store.commit()
        return value

    async def list(self, session: AuthenticatedSession) -> tuple[Conversation, ...]:
        async with self._store_factory() as store:
            return await store.list_for(session.user.id)

    async def messages(
        self, session: AuthenticatedSession, conversation_id: str
    ) -> tuple[ChatMessage, ...]:
        async with self._store_factory() as store:
            await self._owned(store, session.user.id, conversation_id)
            return await store.messages(conversation_id)

    async def delete(
        self, session: AuthenticatedSession, csrf: str | None, conversation_id: str
    ) -> None:
        self._csrf(session, csrf)
        async with self._store_factory() as store:
            await self._owned(store, session.user.id, conversation_id)
            if not await store.delete(conversation_id):
                raise ConversationNotFoundError
            await store.commit()

    async def stream_message(
        self, session: AuthenticatedSession, csrf: str | None, conversation_id: str, content: str
    ) -> AsyncIterator[dict[str, object]]:
        self._csrf(session, csrf)
        content = content.strip()
        if not content or len(content) > 8000:
            raise ConversationError("消息必须包含 1 至 8000 个字符。")
        now = self._clock.now()
        user_message = ChatMessage(new_uuid7(), conversation_id, "user", content, now)
        run = AgentRun(new_uuid7(), conversation_id, user_message.id, "running", now, None)
        async with self._store_factory() as store:
            conversation = await self._owned(store, session.user.id, conversation_id)
            history = await store.messages(conversation_id)
            await store.start(user_message, run)
            await store.event(run.id, 1, "run.started", {"label": "已接收消息"}, now)
            await store.event(
                run.id,
                2,
                "node.started",
                {"node": "context", "label": "正在整理对话上下文"},
                now,
            )
            if conversation.title == "新对话":
                await store.rename(conversation_id, self._title(content), now)
            await store.commit()
        yield {"event": "run.started", "run_id": run.id, "label": "已接收消息"}
        yield {"event": "node.started", "node": "context", "label": "正在整理对话上下文"}
        sequence, chunks = 3, []
        artifacts: list[dict[str, object]] = []
        guide_candidates: dict[str, _GuideCandidateAccumulator] = {}
        place_cards: dict[str, dict[str, object]] = {}
        tool_results: dict[str, ToolResult] = {}
        try:
            await self._event(
                run.id,
                sequence,
                "node.started",
                {"node": "model", "label": "正在请求模型"},
            )
            sequence += 1
            yield {"event": "node.started", "node": "model", "label": "正在请求模型"}
            model_messages: list[dict[str, object]] = [
                {"role": item.role, "content": item.content} for item in history[-20:]
            ]
            model_messages.append({"role": "user", "content": content})
            descriptors = self._tools.model_descriptors()
            completed = False
            total_tool_calls = 0
            for _ in range(4):
                calls: list[ModelStreamEvent] = []
                round_text: list[str] = []
                async for model_event in self._provider.stream_turn(
                    tuple(model_messages), descriptors
                ):
                    if model_event.kind == "text":
                        chunks.append(model_event.text)
                        round_text.append(model_event.text)
                        yield {"event": "assistant.delta", "text": model_event.text}
                    elif model_event.kind == "tool_call":
                        calls.append(model_event)
                if not calls:
                    completed = True
                    break
                model_messages.append(
                    {
                        "role": "assistant",
                        "content": "".join(round_text) or None,
                        "tool_calls": [
                            {
                                "id": call.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": call.tool_name,
                                    "arguments": call.tool_arguments,
                                },
                            }
                            for call in calls
                        ],
                    }
                )
                for call in calls:
                    total_tool_calls += 1
                    label = self._tools.label(call.tool_name)
                    await self._event(
                        run.id,
                        sequence,
                        "tool.started",
                        {"tool": call.tool_name, "label": f"正在{label}"},
                    )
                    sequence += 1
                    yield {
                        "event": "tool.started",
                        "tool": call.tool_name,
                        "label": f"正在{label}",
                    }
                    try:
                        if total_tool_calls > 16:
                            raise ConversationError(
                                "本轮工具调用已达到安全上限, 请基于已有结果总结。"
                            )
                        arguments = json.loads(call.tool_arguments or "{}")
                        if not isinstance(arguments, dict):
                            raise ConversationError("工具参数不是对象。")
                        request_key = _tool_request_key(call.tool_name, arguments)
                        reused = request_key in tool_results
                        if reused:
                            tool_result = tool_results[request_key]
                        else:
                            tool_result = await self._tools.execute(
                                call.tool_name, arguments, session.user.id
                            )
                            tool_results[request_key] = tool_result
                        if call.tool_name == "place_search" and not reused:
                            await self._knowledge.capture_place_results(
                                session.user.id, tool_result.data, "agent_place_search"
                            )
                        result_payload = tool_result.model_payload()
                        cache_label = _result_source_label(tool_result, reused)
                        event_type, event_label = "tool.completed", f"{label}完成 · {cache_label}"
                    except (json.JSONDecodeError, ToolError, ConversationError) as error:
                        result_payload = {
                            "error": str(error) or getattr(error, "code", "tool_error"),
                            "retryable": False,
                        }
                        event_type, event_label = "tool.failed", f"{label}未完成, 已降级"
                    await self._event(
                        run.id,
                        sequence,
                        event_type,
                        {"tool": call.tool_name, "label": event_label},
                    )
                    sequence += 1
                    yield {
                        "event": event_type,
                        "tool": call.tool_name,
                        "label": event_label,
                    }
                    if (
                        event_type == "tool.completed"
                        and call.tool_name == "guide_search_xhs"
                        and not reused
                    ):
                        _collect_guide_candidates(guide_candidates, result_payload)
                    if event_type == "tool.completed" and call.tool_name in {
                        "place_knowledge_upsert",
                        "place_knowledge_batch_upsert",
                    }:
                        tool_data = result_payload.get("data")
                        card_values = (
                            tool_data.get("cards", [])
                            if isinstance(tool_data, dict)
                            and isinstance(tool_data.get("cards"), list)
                            else [tool_data]
                        )
                        for card_value in card_values:
                            if isinstance(card_value, dict) and card_value.get("card_id"):
                                place_cards[str(card_value["card_id"])] = {
                                    key: card_value[key]
                                    for key in ("card_id", "name", "city", "version", "status")
                                    if key in card_value
                                }
                    model_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.tool_call_id,
                            "content": json.dumps(
                                result_payload,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )[:24000],
                        }
                    )
                await self._event(
                    run.id,
                    sequence,
                    "node.started",
                    {"node": "synthesis", "label": "正在结合工具结果"},
                )
                sequence += 1
                yield {
                    "event": "node.started",
                    "node": "synthesis",
                    "label": "正在结合工具结果",
                }
            if not completed:
                await self._event(
                    run.id,
                    sequence,
                    "node.started",
                    {"node": "finalize", "label": "工具调用已结束, 正在整理已完成结果"},
                )
                sequence += 1
                yield {
                    "event": "node.started",
                    "node": "finalize",
                    "label": "工具调用已结束, 正在整理已完成结果",
                }
                model_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "工具调用预算已经结束。请不要再调用工具; 根据已经成功的结果, "
                            "说明完成了哪些内容、哪些未完成以及下一步建议。"
                        ),
                    }
                )
                async for model_event in self._provider.stream_turn(tuple(model_messages), ()):
                    if model_event.kind == "text":
                        chunks.append(model_event.text)
                        yield {"event": "assistant.delta", "text": model_event.text}
            answer = "".join(chunks).strip()
            if not answer:
                raise ConversationError("模型未返回可展示的回答。")
            guide_artifact = _build_guide_artifact(guide_candidates, content)
            if guide_artifact is not None:
                artifacts.append(guide_artifact)
                await self._event(run.id, sequence, "artifact.guides", guide_artifact)
                sequence += 1
                yield {"event": "artifact.guides", "artifact": guide_artifact}
            if place_cards:
                place_artifact: dict[str, object] = {
                    "type": "place_cards",
                    "cards": list(place_cards.values()),
                }
                artifacts.append(place_artifact)
                await self._event(run.id, sequence, "artifact.places", place_artifact)
                sequence += 1
                yield {"event": "artifact.places", "artifact": place_artifact}
            assistant = ChatMessage(
                new_uuid7(), conversation_id, "assistant", answer, self._clock.now()
            )
            async with self._store_factory() as store:
                await store.complete(run.id, assistant, self._clock.now(), tuple(artifacts))
                await store.event(
                    run.id, sequence, "run.completed", {"label": "回答已完成"}, self._clock.now()
                )
                await store.commit()
            yield {"event": "run.completed", "message_id": assistant.id, "label": "回答已完成"}
        except Exception:
            async with self._store_factory() as store:
                await store.fail(run.id, self._clock.now())
                await store.event(
                    run.id, sequence, "run.failed", {"label": "模型请求失败"}, self._clock.now()
                )
                await store.commit()
            yield {
                "event": "run.failed",
                "label": "模型请求失败，请稍后重试。",  # noqa: RUF001
            }

    async def _event(
        self, run_id: str, sequence: int, event_type: str, payload: dict[str, object]
    ) -> None:
        async with self._store_factory() as store:
            await store.event(run_id, sequence, event_type, payload, self._clock.now())
            await store.commit()

    @staticmethod
    async def _owned(store: ConversationStore, user_id: str, conversation_id: str) -> Conversation:
        value = await store.get(conversation_id)
        if value is None:
            raise ConversationNotFoundError
        if value.owner_user_id != user_id:
            raise ConversationPermissionError
        return value

    @staticmethod
    def _csrf(session: AuthenticatedSession, supplied: str | None) -> None:
        if supplied is None or not secrets.compare_digest(session.csrf_token, supplied):
            raise ConversationPermissionError

    @staticmethod
    def _title(content: str) -> str:
        compact = " ".join(content.split())
        return compact[:30] + ("…" if len(compact) > 30 else "")


@dataclass(slots=True)
class _GuideCandidateAccumulator:
    candidate_id: str
    title: str
    author: str
    summary: str
    url: str
    status: str
    score: int
    hits: int
    first_seen: int

    def merge(self, guide: dict[str, object], score: int) -> None:
        self.hits += 1
        self.score += score
        for field in ("title", "author", "summary", "url"):
            incoming = str(guide.get(field) or "").strip()
            current = getattr(self, field)
            if incoming and (not current or len(incoming) > len(current)):
                setattr(self, field, incoming)
        incoming_status = str(guide.get("status") or "").strip()
        if _guide_status_rank(incoming_status) > _guide_status_rank(self.status):
            self.status = incoming_status

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "author": self.author,
            "summary": self.summary,
            "url": self.url,
            "status": self.status,
        }


def _tool_request_key(name: str, arguments: dict[str, object]) -> str:
    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items())}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    return json.dumps(
        [name, normalize(arguments)], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _result_source_label(result: ToolResult, reused: bool) -> str:
    if reused:
        return "复用本轮结果"
    if result.provider.startswith("local_"):
        return {
            "hit": "本地缓存命中",
            "miss": "本地检索",
            "stale": "本地陈旧缓存",
        }.get(result.cache_status, result.cache_status)
    return {
        "hit": "缓存命中",
        "miss": "已联网查询",
        "stale": "过期缓存降级",
    }.get(result.cache_status, result.cache_status)


def _collect_guide_candidates(
    candidates: dict[str, _GuideCandidateAccumulator], payload: dict[str, object]
) -> None:
    data = payload.get("data")
    guides = data.get("guides", []) if isinstance(data, dict) else []
    if not isinstance(guides, list):
        return
    result_count = len(guides)
    for index, raw_guide in enumerate(guides):
        if not isinstance(raw_guide, dict):
            continue
        candidate_id = str(raw_guide.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        score = max(result_count - index, 1)
        existing = candidates.get(candidate_id)
        if existing is not None:
            existing.merge(raw_guide, score)
            continue
        candidates[candidate_id] = _GuideCandidateAccumulator(
            candidate_id=candidate_id,
            title=str(raw_guide.get("title") or "").strip(),
            author=str(raw_guide.get("author") or "").strip(),
            summary=str(raw_guide.get("summary") or "").strip(),
            url=str(raw_guide.get("url") or "").strip(),
            status=str(raw_guide.get("status") or "").strip(),
            score=score,
            hits=1,
            first_seen=len(candidates),
        )


def _build_guide_artifact(
    candidates: dict[str, _GuideCandidateAccumulator], user_content: str
) -> dict[str, object] | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            item.status == "ready",
            -item.hits,
            -item.score,
            item.first_seen,
        ),
    )
    limit = _requested_guide_limit(user_content)
    return {
        "type": "guide_candidates",
        "guides": [candidate.payload() for candidate in ranked[:limit]],
    }


def _requested_guide_limit(content: str) -> int:
    match = re.search(r"(?P<count>10|[1-9]|十|[一二两三四五六七八九])\s*篇", content)
    if match is None:
        return 8
    chinese_counts = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    raw = match.group("count")
    return min(int(raw) if raw.isdigit() else chinese_counts[raw], 10)


def _guide_status_rank(status: str) -> int:
    return {"discovered": 0, "failed": 1, "downloading": 2, "ready": 3}.get(status, 0)
