from __future__ import annotations

import json
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from travel_agent.modules.conversations.domain import AgentRun, ChatMessage, Conversation
from travel_agent.modules.conversations.models import (
    AgentRunEventRow,
    AgentRunRow,
    ConversationMessageArtifactRow,
    ConversationMessageRow,
    ConversationRow,
)
from travel_agent.shared.domain.ids import new_uuid7


class TextProtector(Protocol):
    def encrypt(self, plaintext: str, *, context: str) -> bytes: ...
    def decrypt(self, ciphertext: bytes, *, context: str) -> str: ...


class SqlAlchemyConversationStore:
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
        if self._session:
            if exc_type:
                await self._session.rollback()
            await self._session.close()
        self._session = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Conversation store inactive")
        return self._session

    async def commit(self) -> None:
        await self.session.commit()

    async def create(self, value: Conversation) -> None:
        self.session.add(
            ConversationRow(
                id=value.id,
                owner_user_id=value.owner_user_id,
                title_ciphertext=self._protector.encrypt(value.title, context="conversation.title"),
                created_at=value.created_at,
                updated_at=value.updated_at,
            )
        )

    async def list_for(self, user_id: str) -> tuple[Conversation, ...]:
        rows = await self.session.scalars(
            select(ConversationRow)
            .where(ConversationRow.owner_user_id == user_id)
            .order_by(ConversationRow.updated_at.desc())
        )
        return tuple(self._conversation(row) for row in rows)

    async def get(self, conversation_id: str) -> Conversation | None:
        row = await self.session.get(ConversationRow, conversation_id)
        return self._conversation(row) if row else None

    async def messages(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        rows = tuple(
            await self.session.scalars(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == conversation_id)
                .order_by(ConversationMessageRow.created_at)
            )
        )
        message_ids = [row.id for row in rows]
        artifact_rows = (
            tuple(
                await self.session.scalars(
                    select(ConversationMessageArtifactRow)
                    .where(ConversationMessageArtifactRow.message_id.in_(message_ids))
                    .order_by(ConversationMessageArtifactRow.created_at)
                )
            )
            if message_ids
            else ()
        )
        artifacts: dict[str, list[dict[str, object]]] = {}
        for artifact in artifact_rows:
            payload = json.loads(
                self._protector.decrypt(artifact.payload_ciphertext, context="message.artifact")
            )
            if isinstance(payload, dict):
                artifacts.setdefault(artifact.message_id, []).append(payload)
        return tuple(
            ChatMessage(
                row.id,
                row.conversation_id,
                row.role,
                self._protector.decrypt(row.content_ciphertext, context="conversation.message"),
                row.created_at,
                tuple(artifacts.get(row.id, [])),
            )
            for row in rows
        )

    async def start(self, message: ChatMessage, run: AgentRun) -> None:
        self._add_message(message)
        await self.session.flush()
        self.session.add(
            AgentRunRow(
                id=run.id,
                conversation_id=run.conversation_id,
                user_message_id=run.user_message_id,
                status=run.status,
                created_at=run.created_at,
                completed_at=None,
            )
        )
        await self.session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == message.conversation_id)
            .values(updated_at=message.created_at)
        )

    async def event(
        self,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.session.add(
            AgentRunEventRow(
                id=new_uuid7(),
                run_id=run_id,
                sequence_no=sequence,
                event_type=event_type,
                payload_ciphertext=self._protector.encrypt(text, context="agent.event"),
                created_at=created_at,
            )
        )

    async def complete(
        self,
        run_id: str,
        message: ChatMessage,
        completed_at: datetime,
        artifacts: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._add_message(message)
        await self.session.flush()
        for artifact in artifacts:
            artifact_type = str(artifact.get("type") or "unknown")[:40]
            self.session.add(
                ConversationMessageArtifactRow(
                    id=new_uuid7(),
                    message_id=message.id,
                    artifact_type=artifact_type,
                    payload_ciphertext=self._protector.encrypt(
                        json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
                        context="message.artifact",
                    ),
                    created_at=completed_at,
                )
            )
        await self.session.execute(
            update(AgentRunRow)
            .where(AgentRunRow.id == run_id)
            .values(status="succeeded", completed_at=completed_at)
        )
        await self.session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == message.conversation_id)
            .values(updated_at=completed_at)
        )

    async def fail(self, run_id: str, completed_at: datetime) -> None:
        await self.session.execute(
            update(AgentRunRow)
            .where(AgentRunRow.id == run_id)
            .values(status="failed", completed_at=completed_at)
        )

    async def rename(self, conversation_id: str, title: str, updated_at: datetime) -> None:
        await self.session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == conversation_id)
            .values(
                title_ciphertext=self._protector.encrypt(title, context="conversation.title"),
                updated_at=updated_at,
            )
        )

    def _add_message(self, value: ChatMessage) -> None:
        self.session.add(
            ConversationMessageRow(
                id=value.id,
                conversation_id=value.conversation_id,
                role=value.role,
                content_ciphertext=self._protector.encrypt(
                    value.content, context="conversation.message"
                ),
                created_at=value.created_at,
            )
        )

    def _conversation(self, row: ConversationRow) -> Conversation:
        return Conversation(
            row.id,
            row.owner_user_id,
            self._protector.decrypt(row.title_ciphertext, context="conversation.title"),
            row.created_at,
            row.updated_at,
        )
