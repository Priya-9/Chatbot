from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read; normalise so comparisons with utcnow() work on every backend."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class User(Base):
    """A WhatsApp contact talking to the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(8))
    journey_node: Mapped[str | None] = mapped_column(String(64))
    journey_data: Mapped[dict] = mapped_column(JSON, default=dict)
    customer_ref: Mapped[str | None] = mapped_column(String(64))  # linked CRM customer after OTP verification
    verified_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handoff: Mapped[bool] = mapped_column(Boolean, default=False)  # True -> a human agent owns the chat
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # in | out
    content: Mapped[str] = mapped_column(Text)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)  # inbound only; dedupes retries
    ai: Mapped[bool] = mapped_column(Boolean, default=False)  # part of the LLM conversation memory
    sender: Mapped[str] = mapped_column(String(16), default="bot")  # user | bot | agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="messages")


class Customer(Base):
    """Local customer table: the 'database' side of the CRM integration and the source for OTP login."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    plan: Mapped[str] = mapped_column(String(64), default="Free")
    status: Mapped[str] = mapped_column(String(64), default="active")
    external_id: Mapped[str | None] = mapped_column(String(64))  # id in the external CRM, if any
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    interest: Mapped[str | None] = mapped_column(Text)
    crm_ref: Mapped[str | None] = mapped_column(String(128))
    synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_ref: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentChunk(Base):
    """Knowledge-base chunks used for retrieval (RAG)."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(512), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
