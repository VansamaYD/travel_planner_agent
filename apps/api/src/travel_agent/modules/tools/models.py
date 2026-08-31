from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from travel_agent.shared.infrastructure.db.base import Base


class ExternalCacheRow(Base):
    __tablename__ = "external_cache_entries"
    __table_args__ = (Index("ix_external_cache_expiry", "expires_at", "stale_until"),)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(64))
    scope_hash: Mapped[str] = mapped_column(String(64))
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stale_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class ExternalUsageRow(Base):
    __tablename__ = "external_usage_events"
    __table_args__ = (Index("ix_external_usage_owner_created", "owner_user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(64))
    query_hash: Mapped[str] = mapped_column(String(64))
    cache_status: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[int] = mapped_column(Integer)
    result_count: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GuideCandidateRow(Base):
    __tablename__ = "guide_candidates"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "provider", "external_id_hash", name="uq_guide_candidate_source"
        ),
        Index("ix_guide_candidates_owner_fetched", "owner_user_id", "fetched_at"),
        Index(
            "ix_guide_candidates_owner_status_pinned",
            "owner_user_id",
            "status",
            "pinned",
            "updated_at",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(32))
    external_id_hash: Mapped[str] = mapped_column(String(64))
    external_id_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    access_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_query_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    city_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    title_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    url_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    author_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    summary_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    content_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    images_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    comments_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    tags_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    metadata_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    user_notes_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20), default="discovered")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
