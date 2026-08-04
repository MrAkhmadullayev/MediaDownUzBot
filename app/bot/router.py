import html
import ipaddress
import logging
import uuid
from urllib.parse import urlsplit

import phonenumbers
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from celery import Celery
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    CONTACT_KEYBOARD,
    REMOVE_KEYBOARD,
    admin_link_keyboard,
    audio_quality_keyboard,
    main_keyboard,
    registration_confirmation,
    support_history_keyboard,
    support_menu_keyboard,
    support_ticket_keyboard,
    video_quality_keyboard,
)
from app.bot.states import RegistrationState, SupportState
from app.config import Settings
from app.enums import JobStatus, MediaType, SupportSender, SupportTicketStatus
from app.messages import (
    ADMIN_DENIED,
    ADMIN_LINK,
    ANALYZING,
    CONTACT_INVALID,
    HELP,
    JOB_BUSY,
    JOB_CANCELLED,
    PHONE_INVALID,
    QUALITY_TOO_LARGE,
    QUEUED,
    REGISTRATION_CANCELLED,
    REGISTRATION_REQUIRED,
    REGISTRATION_SUCCESS,
    UNKNOWN_INPUT,
    URL_INVALID,
    WELCOME,
    job_error_message,
)
from app.models import SupportTicket
from app.repositories import (
    AdminRepository,
    JobRepository,
    SupportRepository,
    UserRepository,
)
from app.services.crypto import FieldCipher, create_token, token_hash
from app.services.limits import estimated_size_for, exceeds_upload_limit
from app.services.locks import acquire_active_job, active_job_key, release_active_job
from app.services.urls import InvalidMediaUrlError, parse_media_url

router = Router(name="bot")
logger = logging.getLogger(__name__)


async def touch_user(message: Message, session: AsyncSession):
    telegram_user = message.from_user
    if telegram_user is None:
        return None
    return await UserRepository.touch(
        session,
        telegram_user.id,
        telegram_user.username,
        telegram_user.first_name,
        telegram_user.last_name,
    )


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = await touch_user(message, db_session)
    if user is None:
        return
    if user.is_registered:
        await state.clear()
        await message.answer(
            WELCOME,
            reply_markup=main_keyboard(user.telegram_id in settings.ADMIN_TELEGRAM_IDS),
        )
        return
    await state.set_state(RegistrationState.waiting_contact)
    await message.answer(REGISTRATION_REQUIRED, reply_markup=CONTACT_KEYBOARD)


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Yordam")
async def help_message(
    message: Message,
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = await touch_user(message, db_session)
    if user is None or not user.is_registered:
        await message.answer(REGISTRATION_REQUIRED, reply_markup=CONTACT_KEYBOARD)
        return
    await message.answer(
        HELP,
        reply_markup=main_keyboard(user.telegram_id in settings.ADMIN_TELEGRAM_IDS),
    )


@router.message(RegistrationState.waiting_contact, F.contact)
async def receive_contact(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
) -> None:
    user = await touch_user(message, db_session)
    if user is None or message.contact is None or message.contact.user_id != user.telegram_id:
        await message.answer(CONTACT_INVALID, reply_markup=CONTACT_KEYBOARD)
        return
    phone = normalize_phone(message.contact.phone_number)
    if phone is None:
        await message.answer(PHONE_INVALID, reply_markup=CONTACT_KEYBOARD)
        return
    await state.update_data(phone=phone)
    await state.set_state(RegistrationState.waiting_confirmation)
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    confirmation = (
        "👤 <b>Ma’lumotlaringizni tasdiqlang</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"👤 <b>Ism:</b> {html.escape(full_name)}\n"
        f"📱 <b>Telefon:</b> <code>{html.escape(phone)}</code>\n\n"
        "Ma’lumotlar to‘g‘ri bo‘lsa, tasdiqlash tugmasini bosing."
    )
    await message.answer(confirmation, reply_markup=registration_confirmation())


@router.message(RegistrationState.waiting_contact)
async def contact_required(message: Message) -> None:
    await message.answer(CONTACT_INVALID, reply_markup=CONTACT_KEYBOARD)


@router.callback_query(RegistrationState.waiting_confirmation, F.data == "register:confirm")
async def confirm_registration(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
    cipher: FieldCipher,
    settings: Settings,
) -> None:
    data = await state.get_data()
    phone = data.get("phone")
    telegram_user = callback.from_user
    user = await UserRepository.touch(
        db_session,
        telegram_user.id,
        telegram_user.username,
        telegram_user.first_name,
        telegram_user.last_name,
    )
    if not isinstance(phone, str):
        await callback.answer("Ma’lumot topilmadi", show_alert=True)
        await state.clear()
        return
    await UserRepository.register(db_session, user, cipher.encrypt(phone), phone[-4:])
    await db_session.commit()
    await state.clear()
    await callback.answer("Ro‘yxatdan o‘tildi")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            REGISTRATION_SUCCESS,
            reply_markup=main_keyboard(user.telegram_id in settings.ADMIN_TELEGRAM_IDS),
        )


@router.callback_query(RegistrationState.waiting_confirmation, F.data == "register:cancel")
async def cancel_registration(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(REGISTRATION_CANCELLED, reply_markup=REMOVE_KEYBOARD)


@router.message(F.text == "📊 Admin panel")
async def admin_panel(
    message: Message,
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    user = await touch_user(message, db_session)
    if user is None or user.telegram_id not in settings.ADMIN_TELEGRAM_IDS:
        await message.answer(ADMIN_DENIED)
        return
    raw_token = create_token()
    await AdminRepository.create_login_token(
        db_session,
        user.telegram_id,
        token_hash(raw_token),
        settings.ADMIN_LOGIN_TTL_SECONDS,
    )
    await db_session.commit()
    url = f"{settings.ADMIN_BASE_URL}/admin/login/{raw_token}"
    if is_local_admin_url(url):
        await message.answer(local_admin_link_message(url))
        return
    try:
        await message.answer(ADMIN_LINK, reply_markup=admin_link_keyboard(url))
    except TelegramBadRequest as exc:
        logger.warning(
            "admin_link_keyboard_rejected",
            extra={"error_type": type(exc).__name__},
        )
        await message.answer(local_admin_link_message(url))


@router.message(Command("cancel"))
async def cancel_active_command(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    redis: Redis,
) -> None:
    current_state = await state.get_state()
    if current_state == SupportState.waiting_message.state:
        await state.clear()
        await message.answer("✅ Murojaat yozish bekor qilindi.")
        return
    if current_state:
        await state.clear()
        await message.answer(REGISTRATION_CANCELLED, reply_markup=REMOVE_KEYBOARD)
        return
    if message.from_user is None:
        return
    raw_job_id = await redis.get(active_job_key(message.from_user.id))
    job_id = parse_job_id(raw_job_id)
    if job_id is None:
        await message.answer("ℹ️ Bekor qilinadigan faol vazifa yo‘q.")
        return
    job = await JobRepository.get_owned(db_session, job_id, message.from_user.id, lock=True)
    if job and job.status not in {JobStatus.SUCCESS, JobStatus.ERROR, JobStatus.CANCELLED}:
        await JobRepository.cancel(db_session, job)
        await db_session.commit()
    await release_active_job(redis, message.from_user.id, job_id)
    await message.answer(JOB_CANCELLED)


@router.message(F.text == "💬 Qo‘llab-quvvatlash")
async def support_menu(
    message: Message,
    db_session: AsyncSession,
) -> None:
    user = await touch_user(message, db_session)
    if user is None or not user.is_registered:
        await message.answer(REGISTRATION_REQUIRED, reply_markup=CONTACT_KEYBOARD)
        return
    await message.answer(
        "💬 <b>Qo‘llab-quvvatlash markazi</b>\n\n"
        "Savolingiz yoki muammoingiz bo‘lsa, murojaat yozing. "
        "Javob shu bot orqali keladi va suhbatni davom ettirishingiz mumkin.",
        reply_markup=support_menu_keyboard(),
    )


@router.callback_query(F.data == "support:new")
async def start_support_message(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
) -> None:
    user = await UserRepository.get(db_session, callback.from_user.id)
    if user is None or not user.is_registered:
        await callback.answer("Avval ro‘yxatdan o‘ting", show_alert=True)
        return
    ticket = await SupportRepository.get_open(db_session, user.telegram_id)
    await state.set_state(SupportState.waiting_message)
    await state.update_data(support_ticket_id=str(ticket.id) if ticket else "")
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "✍️ <b>Murojaatingizni yozing</b>\n\n"
            "Muammoni imkon qadar aniq tushuntiring. Bitta xabarda 3 500 belgigacha "
            "matn yuborishingiz mumkin.\n\n"
            "Bekor qilish uchun /cancel buyrug‘ini yuboring."
        )


@router.callback_query(F.data.startswith("support:history"))
async def support_history(
    callback: CallbackQuery,
    db_session: AsyncSession,
) -> None:
    user = await UserRepository.get(db_session, callback.from_user.id)
    if user is None or not user.is_registered:
        await callback.answer("Avval ro‘yxatdan o‘ting", show_alert=True)
        return
    raw_page = (callback.data or "").removeprefix("support:history:")
    page = int(raw_page) if raw_page.isdigit() else 1
    ticket_page = await SupportRepository.list_owned(db_session, user.telegram_id, page)
    await callback.answer()
    if callback.message is None:
        return
    if not ticket_page.items:
        await callback.message.answer(
            "🕘 <b>Murojaatlar tarixi</b>\n\nHozircha murojaatlaringiz yo‘q.",
            reply_markup=support_menu_keyboard(),
        )
        return
    buttons = [
        (
            ticket.id,
            "🟢 Ochiq" if ticket.status == SupportTicketStatus.OPEN else "⚪️ Yopilgan",
            ticket.updated_at.strftime("%d.%m.%Y"),
        )
        for ticket in ticket_page.items
    ]
    await callback.message.answer(
        "🕘 <b>Murojaatlar tarixi</b>\n\n"
        f"Jami {ticket_page.total} ta murojaat · {ticket_page.page}/{ticket_page.pages}-sahifa.",
        reply_markup=support_history_keyboard(buttons, ticket_page.page, ticket_page.pages),
    )


@router.callback_query(F.data.startswith("support:view:"))
async def view_support_ticket(
    callback: CallbackQuery,
    db_session: AsyncSession,
) -> None:
    ticket_id = parse_uuid((callback.data or "").removeprefix("support:view:"))
    ticket = (
        await SupportRepository.get_owned(db_session, ticket_id, callback.from_user.id)
        if ticket_id
        else None
    )
    if ticket is None:
        await callback.answer("Murojaat topilmadi", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        pages = render_support_ticket_pages(ticket)
        for index, page_text in enumerate(pages):
            await callback.message.answer(
                page_text,
                reply_markup=(
                    support_ticket_keyboard(ticket.id) if index == len(pages) - 1 else None
                ),
            )


@router.callback_query(F.data.startswith("support:reply:"))
async def reply_to_support_ticket(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
) -> None:
    ticket_id = parse_uuid((callback.data or "").removeprefix("support:reply:"))
    ticket = (
        await SupportRepository.get_owned(db_session, ticket_id, callback.from_user.id)
        if ticket_id
        else None
    )
    if ticket is None:
        await callback.answer("Murojaat topilmadi", show_alert=True)
        return
    await state.set_state(SupportState.waiting_message)
    await state.update_data(support_ticket_id=str(ticket.id))
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"↩️ <b>#{str(ticket.id)[:8]} murojaatiga javob yozing.</b>\n\n"
            "Bekor qilish uchun /cancel buyrug‘ini yuboring."
        )


@router.message(SupportState.waiting_message, F.text)
async def receive_support_message(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    task_queue: Celery,
) -> None:
    user = await touch_user(message, db_session)
    data = await state.get_data()
    ticket_id = parse_uuid(data.get("support_ticket_id"))
    body = (message.text or "").strip()
    if user is None or not user.is_registered:
        await state.clear()
        await message.answer("❌ Murojaat sessiyasi eskirgan. Qaytadan urinib ko‘ring.")
        return
    if not body:
        await message.answer("❌ Bo‘sh murojaat yuborib bo‘lmaydi.")
        return
    if len(body) > 3500:
        await message.answer("❌ Xabar 3 500 belgidan oshmasligi kerak.")
        return
    ticket = (
        await SupportRepository.get_owned(db_session, ticket_id, user.telegram_id)
        if ticket_id
        else await SupportRepository.get_or_create_open(db_session, user.telegram_id)
    )
    if ticket is None:
        await state.clear()
        await message.answer("❌ Murojaat topilmadi. Qaytadan murojaat yarating.")
        return
    support_message = await SupportRepository.add_message(
        db_session, ticket, SupportSender.USER, body
    )
    await db_session.commit()
    await state.clear()
    try:
        task_queue.send_task(
            "notifications.support.notify_admins",
            args=[str(support_message.id)],
            queue="notifications",
        )
    except Exception as exc:
        logger.error(
            "support_notification_enqueue_failed",
            extra={"message_id": str(support_message.id), "error_type": type(exc).__name__},
        )
    await message.answer(
        "✅ <b>Murojaatingiz qabul qilindi</b>\n\n"
        f"🎫 Raqami: <code>#{str(ticket.id)[:8]}</code>\n"
        "Administrator javobi shu yerga keladi.",
        reply_markup=support_ticket_keyboard(ticket.id),
    )


@router.message(SupportState.waiting_message)
async def support_text_required(message: Message) -> None:
    await message.answer("ℹ️ Murojaatni matn ko‘rinishida yuboring.")


@router.message(StateFilter(None), F.reply_to_message, F.text)
async def continue_support_by_reply(
    message: Message,
    db_session: AsyncSession,
    task_queue: Celery,
) -> None:
    user = await touch_user(message, db_session)
    replied_message = message.reply_to_message
    body = (message.text or "").strip()
    ticket = (
        await SupportRepository.find_owned_by_admin_message(
            db_session, user.telegram_id, replied_message.message_id
        )
        if user and user.is_registered and replied_message
        else None
    )
    if ticket is None:
        await message.answer(
            "ℹ️ Bu xabar qo‘llab-quvvatlash javobi emas. "
            "Murojaat uchun «Qo‘llab-quvvatlash» bo‘limidan foydalaning."
        )
        return
    if not body:
        await message.answer("❌ Bo‘sh javob yuborib bo‘lmaydi.")
        return
    if len(body) > 3500:
        await message.answer("❌ Xabar 3 500 belgidan oshmasligi kerak.")
        return
    support_message = await SupportRepository.add_message(
        db_session, ticket, SupportSender.USER, body
    )
    await db_session.commit()
    try:
        task_queue.send_task(
            "notifications.support.notify_admins",
            args=[str(support_message.id)],
            queue="notifications",
        )
    except Exception as exc:
        logger.error(
            "support_notification_enqueue_failed",
            extra={"message_id": str(support_message.id), "error_type": type(exc).__name__},
        )
    await message.answer(
        "✅ Javobingiz murojaatga qo‘shildi. Administratorga yuborildi.",
        reply_markup=support_ticket_keyboard(ticket.id),
    )


@router.callback_query(F.data.startswith("type:"))
async def choose_media_type(
    callback: CallbackQuery,
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    values = (callback.data or "").split(":")
    if len(values) != 3:
        await callback.answer("Noto‘g‘ri so‘rov", show_alert=True)
        return
    job_id = parse_job_id(values[1])
    job = (
        await JobRepository.get_owned(db_session, job_id, callback.from_user.id) if job_id else None
    )
    if job is None or job.status != JobStatus.WAITING_SELECTION:
        await callback.answer("Bu amal eskirgan", show_alert=True)
        return
    quality_sizes = job.available_quality_sizes or {}
    if values[2] == MediaType.VIDEO.value:
        qualities = job.available_qualities or [360]
        markup = video_quality_keyboard(
            job.id,
            qualities,
            quality_sizes.get("video"),
            settings.upload_limit_bytes,
        )
        prompt = (
            "🎬 <b>Video sifatini tanlang:</b>\n\n"
            "ℹ️ Fayl hajmi taxminiy hisoblangan. 🚫 belgili variant 2 GB limitdan katta."
        )
    elif values[2] == MediaType.AUDIO.value:
        markup = audio_quality_keyboard(
            job.id,
            quality_sizes.get("audio"),
            settings.upload_limit_bytes,
        )
        prompt = (
            "🎵 <b>Audio formatini tanlang:</b>\n\n"
            "ℹ️ Fayl hajmi taxminiy hisoblangan. 🚫 belgili variant 2 GB limitdan katta."
        )
    else:
        await callback.answer("Noto‘g‘ri format", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(prompt, reply_markup=markup)


@router.callback_query(F.data == "oversize")
async def reject_oversized_quality(callback: CallbackQuery) -> None:
    await callback.answer(QUALITY_TOO_LARGE, show_alert=True)


@router.callback_query(F.data.startswith("download:"))
async def queue_download(
    callback: CallbackQuery,
    db_session: AsyncSession,
    redis: Redis,
    task_queue: Celery,
    settings: Settings,
) -> None:
    values = (callback.data or "").split(":")
    if len(values) != 4:
        await callback.answer("Noto‘g‘ri so‘rov", show_alert=True)
        return
    job_id = parse_job_id(values[1])
    try:
        media_type = MediaType(values[2])
    except ValueError:
        media_type = None
    if job_id is None or media_type is None or not valid_quality(media_type, values[3]):
        await callback.answer("Noto‘g‘ri parametr", show_alert=True)
        return
    job = await JobRepository.get_owned(db_session, job_id, callback.from_user.id, lock=True)
    if job is None or job.status != JobStatus.WAITING_SELECTION:
        await callback.answer("Bu amal eskirgan", show_alert=True)
        return
    if media_type == MediaType.VIDEO and int(values[3]) not in (job.available_qualities or []):
        await callback.answer("Bu sifat mavjud emas", show_alert=True)
        return
    estimated_size = estimated_size_for(job.available_quality_sizes, media_type, values[3])
    if exceeds_upload_limit(estimated_size, settings.upload_limit_bytes):
        await callback.answer(QUALITY_TOO_LARGE, show_alert=True)
        return
    job.media_type = media_type
    job.quality = values[3]
    job.status = JobStatus.QUEUED
    await db_session.commit()
    try:
        task_queue.send_task("media.download", args=[str(job.id)], queue="media")
    except Exception as exc:
        logger.error(
            "media_download_enqueue_failed",
            extra={"job_id": str(job.id), "error_type": type(exc).__name__},
        )
        await JobRepository.finish_error(db_session, job, "internal", type(exc).__name__)
        await db_session.commit()
        await release_active_job(redis, callback.from_user.id, job.id)
        await callback.answer("Vazifani navbatga qo‘shib bo‘lmadi", show_alert=True)
        if callback.message:
            await callback.message.edit_text(job_error_message("internal"))
        return
    await callback.answer("Navbatga qo‘shildi")
    if callback.message:
        await callback.message.edit_text(QUEUED)


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_job(
    callback: CallbackQuery,
    db_session: AsyncSession,
    redis: Redis,
) -> None:
    job_id = parse_job_id((callback.data or "").removeprefix("cancel:"))
    job = (
        await JobRepository.get_owned(db_session, job_id, callback.from_user.id, lock=True)
        if job_id
        else None
    )
    if job is None or job.status in {JobStatus.SUCCESS, JobStatus.ERROR, JobStatus.CANCELLED}:
        await callback.answer("Bu amal eskirgan", show_alert=True)
        return
    await JobRepository.cancel(db_session, job)
    await db_session.commit()
    await release_active_job(redis, callback.from_user.id, job.id)
    await callback.answer("Bekor qilindi")
    if callback.message:
        await callback.message.edit_text(JOB_CANCELLED)


@router.message(StateFilter(None), F.text)
async def receive_url(
    message: Message,
    db_session: AsyncSession,
    cipher: FieldCipher,
    redis: Redis,
    task_queue: Celery,
    settings: Settings,
) -> None:
    user = await touch_user(message, db_session)
    if user is None:
        return
    if not user.is_registered:
        await message.answer(REGISTRATION_REQUIRED, reply_markup=CONTACT_KEYBOARD)
        return
    try:
        media_url = parse_media_url(message.text or "")
    except InvalidMediaUrlError:
        await message.answer(URL_INVALID)
        return
    job_id = uuid.uuid4()
    lock_ttl = settings.MAX_DOWNLOAD_SECONDS + 1800
    if not await acquire_active_job(redis, user.telegram_id, job_id, lock_ttl):
        await message.answer(JOB_BUSY)
        return
    try:
        job = await JobRepository.create(
            db_session,
            job_id,
            user.telegram_id,
            cipher.encrypt(media_url.normalized),
            media_url.platform,
        )
        status_message = await message.answer(ANALYZING)
        job.telegram_status_message_id = status_message.message_id
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        await release_active_job(redis, user.telegram_id, job_id)
        raise
    try:
        task_queue.send_task("media.analyze", args=[str(job_id)], queue="media")
    except Exception as exc:
        logger.error(
            "media_analysis_enqueue_failed",
            extra={"job_id": str(job_id), "error_type": type(exc).__name__},
        )
        await JobRepository.finish_error(db_session, job, "internal", type(exc).__name__)
        await db_session.commit()
        await release_active_job(redis, user.telegram_id, job_id)
        await status_message.edit_text(job_error_message("internal"))


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer(UNKNOWN_INPUT)


def normalize_phone(raw_phone: str) -> str | None:
    value = raw_phone.strip().replace(" ", "").replace("-", "")
    if not value.startswith("+"):
        value = f"+{value}"
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def parse_job_id(value: object) -> uuid.UUID | None:
    return parse_uuid(value)


def parse_uuid(value: object) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def render_support_ticket_pages(ticket: SupportTicket) -> list[str]:
    status = "🟢 Ochiq" if ticket.status == SupportTicketStatus.OPEN else "⚪️ Yopilgan"
    entries: list[str] = []
    for item in ticket.messages:
        sender = "👤 Siz" if item.sender == SupportSender.USER else "🛡 Administrator"
        timestamp = item.created_at.strftime("%d.%m.%Y · %H:%M")
        chunks = [item.body[index : index + 500] for index in range(0, len(item.body), 500)]
        for chunk_index, chunk in enumerate(chunks or [""]):
            label = sender if chunk_index == 0 else f"{sender} · davomi"
            entries.append(f"<b>{label}</b> · <i>{timestamp}</i>\n{html.escape(chunk)}")

    buckets: list[list[str]] = [[]]
    bucket_length = 0
    for entry in entries:
        extra_length = len(entry) + (2 if buckets[-1] else 0)
        if buckets[-1] and bucket_length + extra_length > 3400:
            buckets.append([])
            bucket_length = 0
            extra_length = len(entry)
        buckets[-1].append(entry)
        bucket_length += extra_length

    if not entries:
        buckets = [["ℹ️ Bu murojaatda hali xabar yo‘q."]]
    page_count = len(buckets)
    pages = []
    for index, bucket in enumerate(buckets, start=1):
        page_label = f" · {index}/{page_count}" if page_count > 1 else ""
        header = (
            f"💬 <b>Murojaat tafsilotlari{page_label}</b>\n\n"
            f"🎫 <code>#{str(ticket.id)[:8]}</code> · {status}\n"
            f"📅 {ticket.created_at.strftime('%d.%m.%Y · %H:%M')}"
        )
        pages.append(f"{header}\n\n" + "\n\n".join(bucket))
    return pages


def render_support_ticket(ticket: SupportTicket) -> str:
    return render_support_ticket_pages(ticket)[0]


def valid_quality(media_type: MediaType, quality: str) -> bool:
    if media_type == MediaType.AUDIO:
        return quality in {"128", "192", "m4a"}
    try:
        height = int(quality)
    except ValueError:
        return False
    return 144 <= height <= 4320


def is_local_admin_url(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def local_admin_link_message(url: str) -> str:
    return (
        f"{ADMIN_LINK}\n\n"
        f"<b>Lokal test manzili:</b>\n<code>{html.escape(url)}</code>\n\n"
        "Havolani loyiha ishlayotgan kompyuter brauzeriga nusxalang. "
        "Telefondan kirish uchun <code>ADMIN_BASE_URL</code> qiymatini public HTTPS domen "
        "yoki telefon kira oladigan server manziliga almashtiring."
    )
