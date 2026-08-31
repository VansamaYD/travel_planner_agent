from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator, Callable
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
        artifact_signatures: set[tuple[str, ...]] = set()
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
                        arguments = json.loads(call.tool_arguments or "{}")
                        if not isinstance(arguments, dict):
                            raise ConversationError("工具参数不是对象。")
                        tool_result = await self._tools.execute(
                            call.tool_name, arguments, session.user.id
                        )
                        if call.tool_name == "place_search":
                            await self._knowledge.capture_place_results(
                                session.user.id, tool_result.data, "agent_place_search"
                            )
                        result_payload = tool_result.model_payload()
                        cache_label = {
                            "hit": "缓存命中",
                            "miss": "已联网查询",
                            "stale": "过期缓存降级",
                        }.get(tool_result.cache_status, tool_result.cache_status)
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
                    if event_type == "tool.completed" and call.tool_name == "guide_search_xhs":
                        tool_data = result_payload.get("data")
                        guides = tool_data.get("guides", []) if isinstance(tool_data, dict) else []
                        if isinstance(guides, list):
                            candidate_ids = tuple(
                                str(guide.get("candidate_id"))
                                for guide in guides
                                if isinstance(guide, dict) and guide.get("candidate_id")
                            )
                            artifact: dict[str, object] = {
                                "type": "guide_candidates",
                                "guides": [
                                    {
                                        key: value
                                        for key, value in guide.items()
                                        if key
                                        in {
                                            "candidate_id",
                                            "title",
                                            "author",
                                            "summary",
                                            "url",
                                            "status",
                                        }
                                    }
                                    for guide in guides
                                    if isinstance(guide, dict) and guide.get("candidate_id")
                                ],
                            }
                            if artifact["guides"] and candidate_ids not in artifact_signatures:
                                artifact_signatures.add(candidate_ids)
                                artifacts.append(artifact)
                                await self._event(run.id, sequence, "artifact.guides", artifact)
                                sequence += 1
                                yield {"event": "artifact.guides", "artifact": artifact}
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
                raise ConversationError("工具调用轮次超过上限。")
            answer = "".join(chunks).strip()
            if not answer:
                raise ConversationError("模型未返回可展示的回答。")
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
