from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from types import TracebackType
from typing import Protocol

from travel_agent.modules.access.domain.models import AuthenticatedSession
from travel_agent.modules.conversations.domain import AgentRun, ChatMessage, Conversation
from travel_agent.shared.domain.ids import new_uuid7


class ConversationError(Exception):
    code = "conversation_error"


class ConversationNotFoundError(ConversationError):
    code = "conversation_not_found"


class ConversationPermissionError(ConversationError):
    code = "conversation_permission_denied"


class ChatProvider(Protocol):
    def stream(self, messages: tuple[tuple[str, str], ...]) -> AsyncIterator[str]: ...


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
    async def complete(self, run_id: str, message: ChatMessage, completed_at: datetime) -> None: ...
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
        self, store_factory: Callable[[], ConversationStore], provider: ChatProvider, clock: Clock
    ) -> None:
        self._store_factory, self._provider, self._clock = store_factory, provider, clock

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
        try:
            async with self._store_factory() as store:
                await store.event(
                    run.id,
                    sequence,
                    "node.started",
                    {"node": "model", "label": "正在请求模型"},
                    self._clock.now(),
                )
                await store.commit()
            sequence += 1
            yield {"event": "node.started", "node": "model", "label": "正在请求模型"}
            model_messages = (
                *((item.role, item.content) for item in history[-20:]),
                ("user", content),
            )
            async for delta in self._provider.stream(model_messages):
                chunks.append(delta)
                yield {"event": "assistant.delta", "text": delta}
            answer = "".join(chunks).strip()
            assistant = ChatMessage(
                new_uuid7(), conversation_id, "assistant", answer, self._clock.now()
            )
            async with self._store_factory() as store:
                await store.complete(run.id, assistant, self._clock.now())
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
