from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    BOT_TOKEN: SecretStr
    ADMIN_TELEGRAM_IDS: list[int] = Field(min_length=1)
    ADMIN_BASE_URL: str
    ALLOWED_HOSTS: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    DATABASE_URL: str
    ALEMBIC_DATABASE_URL: str
    REDIS_URL: str
    FIELD_ENCRYPTION_KEY: SecretStr
    ADMIN_SESSION_TTL_HOURS: int = Field(default=12, ge=1, le=168)
    ADMIN_LOGIN_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    COOKIE_SECURE: bool = True
    VIDEOS_DIR: Path = Path("/app/videos")
    TELEGRAM_API_BASE_URL: str = "http://telegram-bot-api:8081"
    TELEGRAM_LOCAL_MODE: bool = True
    TELEGRAM_UPLOAD_LIMIT_MB: int = Field(default=2000, ge=1, le=2000)
    TELEGRAM_UPLOAD_TIMEOUT_SECONDS: int = Field(default=3600, ge=60, le=7200)
    MAX_DOWNLOAD_SECONDS: int = Field(default=3600, ge=60, le=3600)
    MAX_VIDEO_HEIGHT: int = Field(default=2160, ge=144, le=4320)
    WORKER_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    MEDIA_METADATA_CACHE_TTL_SECONDS: int = Field(default=86400, ge=300, le=2592000)
    MEDIA_DEDUP_RETRY_SECONDS: int = Field(default=3, ge=1, le=30)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    YTDLP_COOKIES_FILE: Path | None = None
    INSTAGRAM_COOKIES_FILE: Path | None = None

    @field_validator("ADMIN_BASE_URL", "TELEGRAM_API_BASE_URL")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("URL http:// yoki https:// bilan boshlanishi kerak")
        return normalized

    @field_validator("YTDLP_COOKIES_FILE", "INSTAGRAM_COOKIES_FILE", mode="before")
    @classmethod
    def empty_path_to_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def upload_limit_bytes(self) -> int:
        return self.TELEGRAM_UPLOAD_LIMIT_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
