from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PlaceCard:
    id: str
    entity_type: str
    name: str
    city: str
    address: str
    intro: str
    details: dict[str, object]
    longitude: float | None
    latitude: float | None
    confidence: float
    version: int
    last_verified_at: datetime | None
    expires_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImageAnalysis:
    id: str
    source_url: str
    model_name: str
    prompt_version: str
    analysis_mode: str
    status: str
    result: dict[str, object]
    created_at: datetime
    analyzed_at: datetime | None


class KnowledgeError(Exception):
    code = "knowledge_error"


class KnowledgeNotFoundError(KnowledgeError):
    code = "knowledge_not_found"


class VisionUnavailableError(KnowledgeError):
    code = "vision_unavailable"
