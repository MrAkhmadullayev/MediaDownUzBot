import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.enums import JobStatus, MediaType, Platform
from app.models import (
    AdminLoginToken,
    AdminSession,
    DownloadJob,
    MediaSourceCache,
    TelegramFileCache,
    User,
)

TASHKENT = ZoneInfo("Asia/Tashkent")

STATUS_LABELS = {
    JobStatus.PENDING_ANALYSIS: "Tahlil navbatida",
    JobStatus.ANALYZING: "Tahlil qilinmoqda",
    JobStatus.WAITING_SELECTION: "Tanlov kutilmoqda",
    JobStatus.QUEUED: "Navbatda",
    JobStatus.DOWNLOADING: "Yuklanmoqda",
    JobStatus.UPLOADING: "Yuborilmoqda",
    JobStatus.SUCCESS: "Muvaffaqiyatli",
    JobStatus.ERROR: "Xatolik",
    JobStatus.CANCELLED: "Bekor qilingan",
}

MODULES = (
    {
        "key": "users",
        "label": "Foydalanuvchilar",
        "description": "Telegram profillari va ro‘yxatdan o‘tish holati",
        "icon": "users",
    },
    {
        "key": "download_jobs",
        "label": "Media vazifalari",
        "description": "Barcha yuklash jarayonlari va natijalari",
        "icon": "download",
    },
    {
        "key": "media_source_cache",
        "label": "Media metadata keshi",
        "description": "Tahlil qilingan manbalar va sifatlar",
        "icon": "database",
    },
    {
        "key": "telegram_file_cache",
        "label": "Telegram fayl keshi",
        "description": "Qayta yuborish uchun Telegram fayl yozuvlari",
        "icon": "file-video",
    },
    {
        "key": "admin_login_tokens",
        "label": "Kirish havolalari",
        "description": "Bir martalik admin kirish tokenlari",
        "icon": "key-round",
    },
    {
        "key": "admin_sessions",
        "label": "Admin sessiyalari",
        "description": "Faol va muddati tugagan boshqaruv sessiyalari",
        "icon": "shield-check",
    },
)


def module_by_key(key: str) -> dict[str, str]:
    return next(module for module in MODULES if module["key"] == key)


def present_table(view: str, items: list[Any]) -> tuple[list[str], list[list[dict[str, str]]]]:
    presenters = {
        "users": _present_users,
        "download_jobs": _present_jobs,
        "media_source_cache": _present_sources,
        "telegram_file_cache": _present_files,
        "admin_login_tokens": _present_login_tokens,
        "admin_sessions": _present_sessions,
    }
    return presenters[view](items)


def _cell(value: object, kind: str = "text", tone: str = "") -> dict[str, str]:
    return {"value": _text(value), "kind": kind, "tone": tone}


def _text(value: object) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _datetime(value: datetime | None) -> dict[str, str]:
    if value is None:
        return _cell(None, "muted")
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return _cell(aware.astimezone(TASHKENT).strftime("%d.%m.%Y · %H:%M:%S"), "time")


def _boolean(value: bool, true_label: str = "Ha", false_label: str = "Yo‘q") -> dict[str, str]:
    return _cell(true_label if value else false_label, "badge", "success" if value else "neutral")


def _secret(value: object) -> dict[str, str]:
    return _cell(
        "Himoyalangan" if value else "Saqlanmagan",
        "badge",
        "protected" if value else "neutral",
    )


def _bytes(value: int | None) -> dict[str, str]:
    if value is None:
        return _cell(None, "muted")
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for candidate in units:
        unit = candidate
        if size < 1024 or candidate == units[-1]:
            break
        size /= 1024
    precision = 0 if unit == "B" else 2
    return _cell(f"{size:.{precision}f} {unit}", "number")


def _duration(value: int | None) -> dict[str, str]:
    if value is None:
        return _cell(None, "muted")
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        formatted = f"{minutes:02d}:{seconds:02d}"
    return _cell(formatted, "number")


def _json(value: object) -> dict[str, str]:
    if value is None:
        return _cell(None, "muted")
    return _cell(json.dumps(value, ensure_ascii=False, separators=(", ", ": ")), "json")


def _platform(value: Platform) -> dict[str, str]:
    label = "YouTube" if value == Platform.YOUTUBE else "Instagram"
    return _cell(label, "badge", value.value)


def _media_type(value: MediaType | None) -> dict[str, str]:
    if value is None:
        return _cell(None, "muted")
    return _cell("Video" if value == MediaType.VIDEO else "Audio", "badge", value.value)


def _present_users(items: list[User]) -> tuple[list[str], list[list[dict[str, str]]]]:
    columns = [
        "Telegram ID",
        "Username",
        "Ism",
        "Familiya",
        "Telefon ma’lumoti",
        "Telefon oxiri",
        "Ro‘yxatdan o‘tgan",
        "Faol",
        "Yaratilgan",
        "Ro‘yxatdan o‘tgan vaqt",
        "Oxirgi faollik",
    ]
    rows = [
        [
            _cell(item.telegram_id, "code"),
            _cell(f"@{item.username}" if item.username else None),
            _cell(item.first_name),
            _cell(item.last_name),
            _secret(item.phone_encrypted),
            _cell(f"•••• {item.phone_last4}" if item.phone_last4 else None, "code"),
            _boolean(item.is_registered),
            _boolean(item.is_active),
            _datetime(item.created_at),
            _datetime(item.registered_at),
            _datetime(item.last_seen_at),
        ]
        for item in items
    ]
    return columns, rows


def _present_jobs(items: list[DownloadJob]) -> tuple[list[str], list[list[dict[str, str]]]]:
    columns = [
        "Vazifa ID",
        "User ID",
        "Manba URL",
        "Platforma",
        "Holat",
        "Format",
        "Sifat",
        "Sarlavha",
        "Davomiylik",
        "Mavjud sifatlar",
        "Sifat hajmlari",
        "Status xabar ID",
        "Fayl hajmi",
        "Xato kodi",
        "Xato tafsiloti",
        "Yaratilgan",
        "Boshlangan",
        "Yakunlangan",
    ]
    rows = [
        [
            _cell(item.id, "code"),
            _cell(item.user_id, "code"),
            _secret(item.source_url_encrypted),
            _platform(item.platform),
            _cell(STATUS_LABELS[item.status], "badge", item.status.value),
            _media_type(item.media_type),
            _cell(item.quality, "code"),
            _cell(item.title, "wrap"),
            _duration(item.duration_seconds),
            _json(item.available_qualities),
            _json(item.available_quality_sizes),
            _cell(item.telegram_status_message_id, "code"),
            _bytes(item.file_size_bytes),
            _cell(item.error_code, "code"),
            _cell(item.error_detail, "wrap"),
            _datetime(item.created_at),
            _datetime(item.started_at),
            _datetime(item.completed_at),
        ]
        for item in items
    ]
    return columns, rows


def _present_sources(
    items: list[MediaSourceCache],
) -> tuple[list[str], list[list[dict[str, str]]]]:
    columns = [
        "Manba kaliti",
        "Platforma",
        "Sarlavha",
        "Davomiylik",
        "Mavjud sifatlar",
        "Sifat hajmlari",
        "Yangilangan",
    ]
    rows = [
        [
            _cell(item.source_key, "code"),
            _platform(item.platform),
            _cell(item.title, "wrap"),
            _duration(item.duration_seconds),
            _json(item.available_qualities),
            _json(item.available_quality_sizes),
            _datetime(item.updated_at),
        ]
        for item in items
    ]
    return columns, rows


def _present_files(
    items: list[TelegramFileCache],
) -> tuple[list[str], list[list[dict[str, str]]]]:
    columns = [
        "Manba kaliti",
        "Format",
        "Sifat",
        "Telegram file ID",
        "Telegram unique ID",
        "Sarlavha",
        "Davomiylik",
        "Fayl hajmi",
        "Yaratilgan",
        "Oxirgi ishlatilgan",
    ]
    rows = [
        [
            _cell(item.source_key, "code"),
            _media_type(item.media_type),
            _cell(item.quality, "code"),
            _secret(item.telegram_file_id),
            _cell(item.telegram_file_unique_id, "code"),
            _cell(item.title, "wrap"),
            _duration(item.duration_seconds),
            _bytes(item.file_size_bytes),
            _datetime(item.created_at),
            _datetime(item.last_used_at),
        ]
        for item in items
    ]
    return columns, rows


def _present_login_tokens(
    items: list[AdminLoginToken],
) -> tuple[list[str], list[list[dict[str, str]]]]:
    now = datetime.now(UTC)
    columns = [
        "Token ID",
        "Telegram ID",
        "Token hash",
        "Holat",
        "Amal qilish muddati",
        "Ishlatilgan",
        "Yaratilgan",
    ]
    rows = []
    for item in items:
        expires_at = (
            item.expires_at.replace(tzinfo=UTC)
            if item.expires_at.tzinfo is None
            else item.expires_at
        )
        if item.used_at:
            state = _cell("Ishlatilgan", "badge", "neutral")
        elif expires_at <= now:
            state = _cell("Muddati tugagan", "badge", "error")
        else:
            state = _cell("Faol", "badge", "success")
        rows.append(
            [
                _cell(item.id, "code"),
                _cell(item.telegram_id, "code"),
                _secret(item.token_hash),
                state,
                _datetime(item.expires_at),
                _datetime(item.used_at),
                _datetime(item.created_at),
            ]
        )
    return columns, rows


def _present_sessions(
    items: list[AdminSession],
) -> tuple[list[str], list[list[dict[str, str]]]]:
    now = datetime.now(UTC)
    columns = [
        "Sessiya ID",
        "Telegram ID",
        "Session token hash",
        "CSRF hash",
        "Holat",
        "Amal qilish muddati",
        "Oxirgi faollik",
        "Yaratilgan",
    ]
    rows = []
    for item in items:
        expires_at = (
            item.expires_at.replace(tzinfo=UTC)
            if item.expires_at.tzinfo is None
            else item.expires_at
        )
        state = (
            _cell("Faol", "badge", "success")
            if expires_at > now
            else _cell("Muddati tugagan", "badge", "error")
        )
        rows.append(
            [
                _cell(item.id, "code"),
                _cell(item.telegram_id, "code"),
                _secret(item.token_hash),
                _secret(item.csrf_hash),
                state,
                _datetime(item.expires_at),
                _datetime(item.last_seen_at),
                _datetime(item.created_at),
            ]
        )
    return columns, rows
