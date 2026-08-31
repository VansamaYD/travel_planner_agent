from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CacheRecord:
    key_hash: str
    payload: dict[str, object]
    queried_at: datetime
    expires_at: datetime
    stale_until: datetime


@dataclass(frozen=True, slots=True)
class ToolResult:
    data: dict[str, object]
    provider: str
    capability: str
    queried_at: datetime
    expires_at: datetime
    cache_status: str
    warnings: tuple[str, ...] = ()

    def model_payload(self) -> dict[str, object]:
        return {
            "data": self.data,
            "provider": self.provider,
            "capability": self.capability,
            "queried_at": self.queried_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "cache_status": self.cache_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    parameters: dict[str, object]
    provider: str
    ttl_seconds: int
    stale_seconds: int

    def model_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, slots=True)
class GuideCandidate:
    id: str
    provider: str
    title: str
    url: str
    author: str
    summary: str
    city: str
    source_query: str
    status: str
    pinned: bool
    content: str
    images: tuple[str, ...]
    comments: tuple[dict[str, object], ...]
    tags: tuple[str, ...]
    metadata: dict[str, object]
    user_notes: str
    fetched_at: datetime
    expires_at: datetime
    detail_fetched_at: datetime | None
    detail_expires_at: datetime | None


class ToolError(Exception):
    code = "tool_error"


class ToolUnavailableError(ToolError):
    code = "tool_unavailable"


class ToolInputError(ToolError):
    code = "tool_invalid_input"
