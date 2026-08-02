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
    settings = Settings(YTDLP_COOKIES_FILE="")
    assert settings.YTDLP_COOKIES_FILE is None
