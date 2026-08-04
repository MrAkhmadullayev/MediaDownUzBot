import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import (
    BroadcastStatus,
    DeliveryStatus,
    JobStatus,
    MediaType,
    Platform,
    SupportSender,
    SupportTicketStatus,
)


def enum_values(enum_class: type) -> list[str]:
    return [item.value for item in enum_class]


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone_encrypted: Mapped[str | None] = mapped_column(String(512))
    phone_last4: Mapped[str | None] = mapped_column(String(4))
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list["DownloadJob"]] = relationship(back_populates="user")
    support_tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="user")
    broadcast_deliveries: Mapped[list["BroadcastDelivery"]] = relationship(back_populates="user")


class DownloadJob(Base):
    __tablename__ = "download_jobs"
    __table_args__ = (
        Index("ix_download_jobs_user_created", "user_id", "created_at"),
        Index("ix_download_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False)
    source_url_encrypted: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False, values_callable=enum_values), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, values_callable=enum_values),
        default=JobStatus.PENDING_ANALYSIS,
        nullable=False,
    )
    media_type: Mapped[MediaType | None] = mapped_column(
        Enum(MediaType, native_enum=False, values_callable=enum_values)
    )
    quality: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(500))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    available_qualities: Mapped[list[int] | None] = mapped_column(JSON)
    available_quality_sizes: Mapped[dict[str, dict[str, int | None]] | None] = mapped_column(JSON)
    telegram_status_message_id: Mapped[int | None] = mapped_column(BigInteger)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="jobs")


class MediaSourceCache(Base):
    __tablename__ = "media_source_cache"

    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False, values_callable=enum_values), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    available_qualities: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    available_quality_sizes: Mapped[dict[str, dict[str, int | None]]] = mapped_column(
        JSON, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelegramFileCache(Base):
    __tablename__ = "telegram_file_cache"
    __table_args__ = (Index("ix_telegram_file_cache_last_used", "last_used_at"),)

    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, values_callable=enum_values), primary_key=True
    )
    quality: Mapped[str] = mapped_column(String(32), primary_key=True)
    telegram_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminLoginToken(Base):
    __tablename__ = "admin_login_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_user_created", "user_id", "created_at"),
        Index("ix_support_tickets_status_updated", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False)
    status: Mapped[SupportTicketStatus] = mapped_column(
        Enum(SupportTicketStatus, native_enum=False, values_callable=enum_values),
        default=SupportTicketStatus.OPEN,
        server_default=SupportTicketStatus.OPEN.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="support_tickets")
    messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at",
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),
        Index("ix_support_messages_delivery", "delivery_status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    sender: Mapped[SupportSender] = mapped_column(
        Enum(SupportSender, native_enum=False, values_callable=enum_values), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, native_enum=False, values_callable=enum_values),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
        nullable=False,
    )
    error_detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")


class Broadcast(Base):
    __tablename__ = "broadcasts"
    __table_args__ = (Index("ix_broadcasts_created", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(BroadcastStatus, native_enum=False, values_callable=enum_values),
        default=BroadcastStatus.PENDING,
        server_default=BroadcastStatus.PENDING.value,
        nullable=False,
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deliveries: Mapped[list["BroadcastDelivery"]] = relationship(
        back_populates="broadcast",
        cascade="all, delete-orphan",
    )


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        Index("ix_broadcast_deliveries_status", "broadcast_id", "status"),
        Index("ix_broadcast_deliveries_user", "user_id", "created_at"),
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_delivery_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, native_enum=False, values_callable=enum_values),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
        nullable=False,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    error_detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    broadcast: Mapped[Broadcast] = relationship(back_populates="deliveries")
    user: Mapped[User] = relationship(back_populates="broadcast_deliveries")
