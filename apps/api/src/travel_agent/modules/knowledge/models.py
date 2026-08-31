from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from travel_agent.shared.infrastructure.db.base import Base


class PlaceKnowledgeCardRow(Base):
    __tablename__ = "place_knowledge_cards"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "identity_hash", name="uq_place_knowledge_identity"),
        Index("ix_place_knowledge_owner_updated", "owner_user_id", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    identity_hash: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(24))
    name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    city_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    address_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    intro_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    details_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlaceKnowledgeRevisionRow(Base):
    __tablename__ = "place_knowledge_revisions"
    __table_args__ = (UniqueConstraint("card_id", "version", name="uq_place_knowledge_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("place_knowledge_cards.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(80))
    snapshot_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImageAnalysisRow(Base):
    __tablename__ = "image_analysis_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "image_identity_hash",
            "model_name",
            "prompt_version",
            name="uq_image_analysis_identity",
        ),
        Index("ix_image_analysis_owner_created", "owner_user_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    image_identity_hash: Mapped[str] = mapped_column(String(64))
    source_url_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    analysis_mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(20))
    result_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    error_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
