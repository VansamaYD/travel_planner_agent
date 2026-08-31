from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from travel_agent.shared.infrastructure.db.base import Base


class SystemStateRow(Base):
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_code_hash: Mapped[str | None] = mapped_column(Text)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username_normalized: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    display_name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    password_hash: Mapped[str] = mapped_column(Text)
    system_role: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(16), default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FamilyRow(Base):
    __tablename__ = "families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    default_locale: Mapped[str] = mapped_column(String(16), default="zh-CN")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    storage_limit_bytes: Mapped[int] = mapped_column(Integer, default=20 * 1024**3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FamilyMembershipRow(Base):
    __tablename__ = "family_memberships"
    __table_args__ = (Index("uq_family_membership", "family_id", "user_id", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TravelerProfileRow(Base):
    __tablename__ = "traveler_profiles"

    membership_id: Mapped[str] = mapped_column(
        ForeignKey("family_memberships.id", ondelete="CASCADE"), primary_key=True
    )
    profile_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FamilyInviteRow(Base):
    __tablename__ = "family_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), index=True)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_epoch: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(24), index=True)
    subject_type: Mapped[str] = mapped_column(String(40), index=True)
    subject_id: Mapped[str | None] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
