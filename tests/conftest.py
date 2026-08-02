import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("BOT_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "[123456789]")
os.environ.setdefault("ADMIN_BASE_URL", "http://localhost:8080")
os.environ.setdefault("ALLOWED_HOSTS", '["localhost","127.0.0.1","testserver"]')
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("TELEGRAM_API_BASE_URL", "http://telegram-bot-api:8081")
os.environ.setdefault("TELEGRAM_LOCAL_MODE", "true")
os.environ.setdefault("TELEGRAM_UPLOAD_LIMIT_MB", "2000")
os.environ.setdefault("TELEGRAM_UPLOAD_TIMEOUT_SECONDS", "3600")
