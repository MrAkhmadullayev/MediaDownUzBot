import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_normalizes_admin_url() -> None:
    settings = Settings(
        ADMIN_BASE_URL="https://example.com/",
        TELEGRAM_UPLOAD_LIMIT_MB=49,
    )
    assert settings.ADMIN_BASE_URL == "https://example.com"
    assert settings.upload_limit_bytes == 49 * 1024 * 1024


def test_local_telegram_api_settings() -> None:
    settings = Settings(TELEGRAM_API_BASE_URL="http://telegram-bot-api:8081/")

    assert settings.TELEGRAM_API_BASE_URL == "http://telegram-bot-api:8081"
    assert settings.TELEGRAM_LOCAL_MODE is True
    assert settings.TELEGRAM_UPLOAD_LIMIT_MB == 2000
    assert settings.TELEGRAM_UPLOAD_TIMEOUT_SECONDS == 3600


def test_empty_cookie_path_is_none() -> None:
    settings = Settings(
        YTDLP_COOKIES_FILE="",
        YTDLP_POT_PROVIDER_URL="",
        YTDLP_PROXY_URL="",
        INSTAGRAM_COOKIES_FILE="",
    )
    assert settings.YTDLP_COOKIES_FILE is None
    assert settings.YTDLP_POT_PROVIDER_URL is None
    assert settings.YTDLP_PROXY_URL is None
    assert settings.INSTAGRAM_COOKIES_FILE is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("YTDLP_POT_PROVIDER_URL", "file:///tmp/provider"),
        ("YTDLP_POT_PROVIDER_URL", "http://user:password@provider:4416"),
        ("YTDLP_PROXY_URL", "ftp://proxy.example"),
        ("YTDLP_PROXY_URL", "https://proxy.example/ bad"),
    ],
)
def test_invalid_ytdlp_service_urls_are_rejected(field, value) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
