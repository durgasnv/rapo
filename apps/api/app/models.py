from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('participant', 'organizer')", name="user_role"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="participant")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int]
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("min_team_size >= 1 AND max_team_size >= min_team_size", name="team_sizes"),
        CheckConstraint("capacity IS NULL OR capacity >= min_team_size", name="event_capacity"),
        CheckConstraint("start_at < end_at", name="event_dates"),
        CheckConstraint(
            "registration_opens_at < registration_closes_at AND registration_closes_at <= start_at",
            name="registration_dates",
        ),
        CheckConstraint(
            "grouping_at >= registration_closes_at AND grouping_at <= confirmation_deadline "
            "AND confirmation_deadline <= start_at",
            name="grouping_dates",
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'CANCELLED')", name="event_status"),
        Index("ix_events_status_start_at", "status", "start_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organizer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(500), default="")
    timezone: Mapped[str] = mapped_column(String(100))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grouping_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmation_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int | None]
    min_team_size: Mapped[int]
    max_team_size: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), index=True)
    action: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
