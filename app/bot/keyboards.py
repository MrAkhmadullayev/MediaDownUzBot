import uuid

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.services.limits import exceeds_upload_limit

CONTACT_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Telefon raqamingizni yuboring",
)

REMOVE_KEYBOARD = ReplyKeyboardRemove()


def main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text="ℹ️ Yordam"),
            KeyboardButton(text="💬 Qo‘llab-quvvatlash"),
        ]
    ]
    if is_admin:
        rows.append([KeyboardButton(text="📊 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def registration_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="register:confirm"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="register:cancel"),
            ]
        ]
    )


def media_type_keyboard(job_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Video", callback_data=f"type:{job_id}:video"),
                InlineKeyboardButton(text="🎵 Audio", callback_data=f"type:{job_id}:audio"),
            ],
            [InlineKeyboardButton(text="🛑 Bekor qilish", callback_data=f"cancel:{job_id}")],
        ]
    )


def video_quality_keyboard(
    job_id: uuid.UUID,
    qualities: list[int],
    quality_sizes: dict[str, int | None] | None = None,
    upload_limit_bytes: int | None = None,
) -> InlineKeyboardMarkup:
    sizes = quality_sizes or {}
    rows = [
        [
            download_option_button(
                label=f"{quality}p",
                callback_data=f"download:{job_id}:video:{quality}",
                size_bytes=sizes.get(str(quality)),
                upload_limit_bytes=upload_limit_bytes,
            )
        ]
        for quality in qualities
    ]
    rows.append([InlineKeyboardButton(text="🛑 Bekor qilish", callback_data=f"cancel:{job_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def audio_quality_keyboard(
    job_id: uuid.UUID,
    quality_sizes: dict[str, int | None] | None = None,
    upload_limit_bytes: int | None = None,
) -> InlineKeyboardMarkup:
    sizes = quality_sizes or {}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                download_option_button(
                    label="MP3 · 128 kbps",
                    callback_data=f"download:{job_id}:audio:128",
                    size_bytes=sizes.get("128"),
                    upload_limit_bytes=upload_limit_bytes,
                )
            ],
            [
                download_option_button(
                    label="MP3 · 192 kbps",
                    callback_data=f"download:{job_id}:audio:192",
                    size_bytes=sizes.get("192"),
                    upload_limit_bytes=upload_limit_bytes,
                )
            ],
            [
                download_option_button(
                    label="M4A · yuqori sifat",
                    callback_data=f"download:{job_id}:audio:m4a",
                    size_bytes=sizes.get("m4a"),
                    upload_limit_bytes=upload_limit_bytes,
                )
            ],
            [InlineKeyboardButton(text="🛑 Bekor qilish", callback_data=f"cancel:{job_id}")],
        ]
    )


def download_option_button(
    label: str,
    callback_data: str,
    size_bytes: int | None,
    upload_limit_bytes: int | None,
) -> InlineKeyboardButton:
    size_label = format_estimated_size(size_bytes)
    if upload_limit_bytes is not None and exceeds_upload_limit(size_bytes, upload_limit_bytes):
        return InlineKeyboardButton(
            text=f"🚫 {label} · {size_label} · hajm katta",
            callback_data="oversize",
        )
    return InlineKeyboardButton(
        text=f"{label} · {size_label}",
        callback_data=callback_data,
    )


def format_estimated_size(size_bytes: int | None) -> str:
    if not size_bytes or size_bytes < 1:
        return "hajm noma’lum"
    if size_bytes >= 1024 * 1024 * 1024:
        return f"≈ {size_bytes / (1024 * 1024 * 1024):.2f} GB"
    return f"≈ {size_bytes / (1024 * 1024):.1f} MB"


def admin_link_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔐 Admin panelni ochish", url=url)]]
    )


def support_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Murojaat qilish", callback_data="support:new")],
            [InlineKeyboardButton(text="🕘 Murojaatlar tarixi", callback_data="support:history")],
        ]
    )


def support_history_keyboard(
    tickets: list[tuple[uuid.UUID, str, str]],
    page: int,
    pages: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{status} #{str(ticket_id)[:8]} · {updated_at}",
                callback_data=f"support:view:{ticket_id}",
            )
        ]
        for ticket_id, status, updated_at in tickets
    ]
    pagination = []
    if page > 1:
        pagination.append(
            InlineKeyboardButton(text="‹ Oldingi", callback_data=f"support:history:{page - 1}")
        )
    if page < pages:
        pagination.append(
            InlineKeyboardButton(text="Keyingi ›", callback_data=f"support:history:{page + 1}")
        )
    if pagination:
        rows.append(pagination)
    rows.append([InlineKeyboardButton(text="✍️ Murojaat qilish", callback_data="support:new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_ticket_keyboard(ticket_id: uuid.UUID, can_reply: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_reply:
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ Shu murojaatga javob yozish",
                    callback_data=f"support:reply:{ticket_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🕘 Barcha murojaatlar", callback_data="support:history")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
