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
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import JobStatus, MediaType, Platform


def enum_values(enum_class: type[Platform | MediaType | JobStatus]) -> list[str]:
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
