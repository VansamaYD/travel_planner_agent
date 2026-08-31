from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    owner_user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: str
    conversation_id: str
    user_message_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None
