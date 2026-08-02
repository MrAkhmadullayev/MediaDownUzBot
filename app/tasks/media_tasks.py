import asyncio
import html
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import FSInputFile, InputFile, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.client import create_bot
from app.bot.keyboards import media_type_keyboard
from app.config import Settings, get_settings
from app.database import Database
from app.enums import JobStatus, MediaType, Platform
from app.messages import CACHE_WAITING, DOWNLOADING, UPLOADING, job_error_message
from app.models import DownloadJob, TelegramFileCache
from app.repositories import JobRepository, MediaCacheRepository, selected_quality
from app.services.crypto import FieldCipher
from app.services.limits import exceeds_upload_limit
from app.services.locks import (
    acquire_media_download,
    release_active_job,
    release_media_download,
)
from app.services.media import (
    DownloadedMedia,
    MediaInfo,
    MediaProcessingError,
    MediaService,
    platform_label,
)
from app.services.urls import media_source_key
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DownloadContext:
    user_id: int
    status_message_id: int | None
    media_type: MediaType
    quality: str
    platform: Platform
    url: str
    source_key: str


def run_async(coroutine: object) -> object:
    return asyncio.run(coroutine)


def log_timing(
    message: str,
    job_id: uuid.UUID,
    stage: str,
    started_at: float,
    *,
    size_bytes: int | None = None,
    cache_hit: bool = False,
) -> None:
    extra: dict[str, object] = {
        "job_id": str(job_id),
        "stage": stage,
        "elapsed_seconds": round(monotonic() - started_at, 3),
        "cache_hit": cache_hit,
    }
    if size_bytes is not None:
        extra["size_bytes"] = size_bytes
    logger.info(message, extra=extra)


async def edit_or_send(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    text: str,
    reply_markup: object | None = None,
) -> int | None:
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return message_id
        except TelegramAPIError:
            pass
    try:
        message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return message.message_id
    except TelegramAPIError:
        return None


async def analyze_job(job_id: uuid.UUID) -> None:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings)
    cipher = FieldCipher(settings.FIELD_ENCRYPTION_KEY.get_secret_value())
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    analysis_started = monotonic()
    try:
        async with database.session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None or job.status != JobStatus.PENDING_ANALYSIS:
                return
            job.status = JobStatus.ANALYZING
            job.started_at = datetime.now(UTC)
            encrypted_url = job.source_url_encrypted
            user_id = job.user_id
            platform = job.platform
            status_message_id = job.telegram_status_message_id
            await session.commit()
        if not encrypted_url:
            raise MediaProcessingError("invalid_media")
        url = cipher.decrypt(encrypted_url)
        source_key = media_source_key(url)
        cache_hit = False
        async with database.session_factory() as session:
            cached_source = await MediaCacheRepository.get_source(
                session,
                source_key,
                settings.MEDIA_METADATA_CACHE_TTL_SECONDS,
            )
            if cached_source and cached_source.platform == platform:
                info = MediaInfo(
                    title=cached_source.title,
                    duration_seconds=cached_source.duration_seconds,
                    qualities=list(cached_source.available_qualities),
                    quality_sizes=dict(cached_source.available_quality_sizes),
                )
                cache_hit = True
            else:
                probe_started = monotonic()
                info = await asyncio.to_thread(MediaService(settings).probe, url)
                log_timing("media_probe_completed", job_id, "probe", probe_started)
                await MediaCacheRepository.upsert_source(
                    session,
                    source_key,
                    platform,
                    info.title,
                    info.duration_seconds,
                    info.qualities,
                    info.quality_sizes,
                )
                await session.commit()
        async with database.session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None or job.status != JobStatus.ANALYZING:
                return
            job.title = info.title
            job.duration_seconds = info.duration_seconds
            job.available_qualities = info.qualities
            job.available_quality_sizes = info.quality_sizes
            automatic_selection = automatic_download_selection(
                job.platform,
                info,
                settings.upload_limit_bytes,
            )
            if automatic_selection:
                job.media_type, job.quality = automatic_selection
                job.status = JobStatus.QUEUED
            else:
                job.status = JobStatus.WAITING_SELECTION
            await session.commit()
        log_timing(
            "media_analysis_completed",
            job_id,
            "analysis",
            analysis_started,
            cache_hit=cache_hit,
        )
        duration = format_duration(info.duration_seconds)
        if automatic_selection:
            text = (
                "✅ <b>Instagram mediasi topildi</b>\n\n"
                f"🎞 <b>Nomi:</b> {html.escape(info.title[:180])}\n"
                f"⏱ <b>Davomiyligi:</b> {duration}\n"
                f"⚙️ <b>Sifat:</b> {selected_quality(*automatic_selection)}\n\n"
                "🕐 <b>Vazifa navbatga qo‘shildi.</b>"
            )
            new_message_id = await edit_or_send(bot, user_id, status_message_id, text)
            if new_message_id and new_message_id != status_message_id:
                await update_status_message(database, job_id, new_message_id)
            try:
                celery_app.send_task("media.download", args=[str(job_id)], queue="media")
            except Exception as exc:
                logger.error(
                    "media_download_enqueue_failed",
                    extra={"job_id": str(job_id), "error_type": type(exc).__name__},
                )
                await fail_job(database, bot, redis, job_id, "internal", type(exc).__name__)
            return
        text = (
            "✅ <b>Media topildi</b>\n\n"
            f"🎞 <b>Nomi:</b> {html.escape(info.title[:180])}\n"
            f"⏱ <b>Davomiyligi:</b> {duration}\n\n"
            "Kerakli formatni tanlang:"
        )
        new_message_id = await edit_or_send(
            bot,
            user_id,
            status_message_id,
            text,
            media_type_keyboard(job_id),
        )
        if new_message_id and new_message_id != status_message_id:
            await update_status_message(database, job_id, new_message_id)
    except MediaProcessingError as exc:
        await fail_job(database, bot, redis, job_id, exc.code, exc.detail)
    except Exception as exc:
        logger.error(
            "media_analysis_failed",
            extra={"job_id": str(job_id), "error_type": type(exc).__name__},
        )
        await fail_job(database, bot, redis, job_id, "internal", type(exc).__name__)
    finally:
        await bot.session.close()
        await redis.aclose()
        await database.close()


async def download_job(job_id: uuid.UUID) -> bool:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings)
    cipher = FieldCipher(settings.FIELD_ENCRYPTION_KEY.get_secret_value())
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    media_service = MediaService(settings)
    context: DownloadContext | None = None
    lock_acquired = False
    task_started = monotonic()
    try:
        context = await load_download_context(database, cipher, job_id)
        if context is None:
            return False
        cached_file = await get_cached_file(
            database,
            context.source_key,
            context.media_type,
            context.quality,
        )
        if cached_file and await deliver_cached_file(
            database,
            bot,
            redis,
            settings,
            job_id,
            context,
            cached_file,
        ):
            log_timing(
                "media_job_completed",
                job_id,
                "total",
                task_started,
                size_bytes=cached_file.file_size_bytes,
                cache_hit=True,
            )
            return False
        lock_acquired = await acquire_media_download(
            redis,
            context.source_key,
            context.media_type.value,
            context.quality,
            job_id,
            settings.MAX_DOWNLOAD_SECONDS + 120,
        )
        if not lock_acquired:
            await edit_or_send(
                bot,
                context.user_id,
                context.status_message_id,
                CACHE_WAITING,
            )
            logger.info(
                "media_download_deduplicated",
                extra={"job_id": str(job_id), "stage": "dedup_wait", "cache_hit": False},
            )
            return True
        cached_file = await get_cached_file(
            database,
            context.source_key,
            context.media_type,
            context.quality,
        )
        if cached_file and await deliver_cached_file(
            database,
            bot,
            redis,
            settings,
            job_id,
            context,
            cached_file,
        ):
            log_timing(
                "media_job_completed",
                job_id,
                "total",
                task_started,
                size_bytes=cached_file.file_size_bytes,
                cache_hit=True,
            )
            return False
        if not await mark_downloading(database, job_id):
            return False
        await edit_or_send(bot, context.user_id, context.status_message_id, DOWNLOADING)
        download_started = monotonic()
        downloaded = await asyncio.to_thread(
            media_service.download,
            context.url,
            job_id,
            context.media_type,
            context.quality,
        )
        log_timing(
            "media_source_download_completed",
            job_id,
            "download",
            download_started,
            size_bytes=downloaded.size_bytes,
        )
        if not await mark_uploading(database, job_id, downloaded.size_bytes):
            return False
        await edit_or_send(bot, context.user_id, context.status_message_id, UPLOADING)
        upload_started = monotonic()
        try:
            message = await send_media(
                bot,
                settings,
                context,
                upload_input(downloaded, settings),
                downloaded.title,
                downloaded.duration_seconds,
            )
        except TelegramAPIError as exc:
            raise MediaProcessingError("upload_failed", type(exc).__name__) from None
        log_timing(
            "telegram_upload_completed",
            job_id,
            "upload",
            upload_started,
            size_bytes=downloaded.size_bytes,
        )
        completed = await save_delivery_result(database, job_id, context, downloaded, message)
        if completed:
            await show_completed(bot, context)
        await release_active_job(redis, context.user_id, job_id)
        log_timing(
            "media_job_completed",
            job_id,
            "total",
            task_started,
            size_bytes=downloaded.size_bytes,
        )
        return False
    except MediaProcessingError as exc:
        await fail_job(database, bot, redis, job_id, exc.code, exc.detail)
        return False
    except Exception as exc:
        logger.error(
            "media_download_failed",
            extra={"job_id": str(job_id), "error_type": type(exc).__name__},
        )
        await fail_job(database, bot, redis, job_id, "internal", type(exc).__name__)
        return False
    finally:
        if lock_acquired and context:
            try:
                await release_media_download(
                    redis,
                    context.source_key,
                    context.media_type.value,
                    context.quality,
                    job_id,
                )
            except Exception as exc:
                logger.error(
                    "media_download_lock_release_failed",
                    extra={"job_id": str(job_id), "error_type": type(exc).__name__},
                )
        try:
            media_service.cleanup(job_id)
        except Exception as exc:
            logger.error(
                "media_cleanup_failed",
                extra={"job_id": str(job_id), "error_type": type(exc).__name__},
            )
        await close_download_resources(bot, redis, database, job_id)


async def close_download_resources(
    bot: Bot,
    redis: Redis,
    database: Database,
    job_id: uuid.UUID,
) -> None:
    resources = (
        ("bot", bot.session.close),
        ("redis", redis.aclose),
        ("database", database.close),
    )
    for resource_name, close in resources:
        try:
            await close()
        except Exception as exc:
            logger.error(
                "media_resource_close_failed",
                extra={
                    "job_id": str(job_id),
                    "resource": resource_name,
                    "error_type": type(exc).__name__,
                },
            )


async def load_download_context(
    database: Database,
    cipher: FieldCipher,
    job_id: uuid.UUID,
) -> DownloadContext | None:
    async with database.session_factory() as session:
        job = await session.get(DownloadJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return None
        if not job.source_url_encrypted or not job.media_type or not job.quality:
            raise MediaProcessingError("invalid_media")
        url = cipher.decrypt(job.source_url_encrypted)
        return DownloadContext(
            user_id=job.user_id,
            status_message_id=job.telegram_status_message_id,
            media_type=job.media_type,
            quality=job.quality,
            platform=job.platform,
            url=url,
            source_key=media_source_key(url),
        )


async def get_cached_file(
    database: Database,
    source_key: str,
    media_type: MediaType,
    quality: str,
) -> TelegramFileCache | None:
    async with database.session_factory() as session:
        return await MediaCacheRepository.get_file(session, source_key, media_type, quality)


async def deliver_cached_file(
    database: Database,
    bot: Bot,
    redis: Redis,
    settings: Settings,
    job_id: uuid.UUID,
    context: DownloadContext,
    cached_file: TelegramFileCache,
) -> bool:
    if not await mark_uploading(database, job_id, cached_file.file_size_bytes):
        return True
    await edit_or_send(bot, context.user_id, context.status_message_id, UPLOADING)
    upload_started = monotonic()
    try:
        await send_media(
            bot,
            settings,
            context,
            cached_file.telegram_file_id,
            cached_file.title,
            cached_file.duration_seconds,
        )
    except TelegramBadRequest:
        async with database.session_factory() as session:
            await MediaCacheRepository.delete_file(
                session,
                context.source_key,
                context.media_type,
                context.quality,
            )
            job = await session.get(DownloadJob, job_id)
            if job and job.status == JobStatus.UPLOADING:
                job.status = JobStatus.QUEUED
            await session.commit()
        logger.warning(
            "telegram_file_cache_invalidated",
            extra={"job_id": str(job_id), "stage": "cache_send"},
        )
        return False
    except TelegramAPIError as exc:
        raise MediaProcessingError("upload_failed", type(exc).__name__) from None
    async with database.session_factory() as session:
        await MediaCacheRepository.touch_file(
            session,
            context.source_key,
            context.media_type,
            context.quality,
        )
        completed = await finish_success(session, job_id, cached_file.file_size_bytes)
        await session.commit()
    if completed:
        await show_completed(bot, context)
    await release_active_job(redis, context.user_id, job_id)
    log_timing(
        "telegram_cached_send_completed",
        job_id,
        "cache_send",
        upload_started,
        size_bytes=cached_file.file_size_bytes,
        cache_hit=True,
    )
    return True


async def mark_downloading(database: Database, job_id: uuid.UUID) -> bool:
    async with database.session_factory() as session:
        changed = await JobRepository.transition(
            session,
            job_id,
            {JobStatus.QUEUED},
            JobStatus.DOWNLOADING,
            started_at=datetime.now(UTC),
        )
        await session.commit()
        return changed


async def mark_uploading(
    database: Database,
    job_id: uuid.UUID,
    size_bytes: int | None,
) -> bool:
    async with database.session_factory() as session:
        changed = await JobRepository.transition(
            session,
            job_id,
            {JobStatus.QUEUED, JobStatus.DOWNLOADING},
            JobStatus.UPLOADING,
            file_size_bytes=size_bytes,
        )
        await session.commit()
        return changed


async def finish_success(
    session: AsyncSession,
    job_id: uuid.UUID,
    size_bytes: int | None,
) -> bool:
    changed = await JobRepository.transition(
        session,
        job_id,
        {JobStatus.UPLOADING},
        JobStatus.SUCCESS,
        source_url_encrypted=None,
        file_size_bytes=size_bytes,
        error_code=None,
        error_detail=None,
        completed_at=datetime.now(UTC),
    )
    return changed


def upload_input(downloaded: DownloadedMedia, settings: Settings) -> str | InputFile:
    if settings.TELEGRAM_LOCAL_MODE:
        return downloaded.path.resolve().as_uri()
    return FSInputFile(downloaded.path)


async def send_media(
    bot: Bot,
    settings: Settings,
    context: DownloadContext,
    media: str | InputFile,
    title: str,
    duration_seconds: int | None,
) -> Message:
    caption = (
        "✅ <b>Tayyor!</b>\n\n"
        f"🎞 <b>Nomi:</b> {html.escape(title[:180])}\n"
        f"🌐 <b>Manba:</b> {platform_label(context.platform)}\n"
        f"⚙️ <b>Sifat:</b> {selected_quality(context.media_type, context.quality)}"
    )
    if context.media_type == MediaType.VIDEO:
        return await bot.send_video(
            chat_id=context.user_id,
            video=media,
            caption=caption,
            duration=duration_seconds,
            supports_streaming=True,
            request_timeout=settings.TELEGRAM_UPLOAD_TIMEOUT_SECONDS,
        )
    return await bot.send_audio(
        chat_id=context.user_id,
        audio=media,
        caption=caption,
        title=title[:64],
        duration=duration_seconds,
        request_timeout=settings.TELEGRAM_UPLOAD_TIMEOUT_SECONDS,
    )


async def save_delivery_result(
    database: Database,
    job_id: uuid.UUID,
    context: DownloadContext,
    downloaded: DownloadedMedia,
    message: Message,
) -> bool:
    telegram_media = message.video if context.media_type == MediaType.VIDEO else message.audio
    async with database.session_factory() as session:
        if telegram_media:
            await MediaCacheRepository.upsert_file(
                session,
                context.source_key,
                context.media_type,
                context.quality,
                telegram_media.file_id,
                telegram_media.file_unique_id,
                downloaded.title,
                downloaded.duration_seconds,
                downloaded.size_bytes,
            )
        completed = await finish_success(session, job_id, downloaded.size_bytes)
        await session.commit()
        return completed


async def show_completed(bot: Bot, context: DownloadContext) -> None:
    await edit_or_send(
        bot,
        context.user_id,
        context.status_message_id,
        "✅ <b>Vazifa muvaffaqiyatli yakunlandi.</b>\n\nYangi havola yuborishingiz mumkin.",
    )


async def fail_job(
    database: Database,
    bot: Bot,
    redis: Redis,
    job_id: uuid.UUID,
    code: str,
    detail: str | None,
) -> None:
    async with database.session_factory() as session:
        job = await session.get(DownloadJob, job_id)
        if job is None:
            return
        user_id = job.user_id
        message_id = job.telegram_status_message_id
        if job.status in {JobStatus.SUCCESS, JobStatus.CANCELLED}:
            await release_active_job(redis, user_id, job_id)
            return
        await JobRepository.finish_error(session, job, code, detail)
        await session.commit()
    await edit_or_send(bot, user_id, message_id, job_error_message(code))
    await release_active_job(redis, user_id, job_id)


async def update_status_message(database: Database, job_id: uuid.UUID, message_id: int) -> None:
    async with database.session_factory() as session:
        job = await session.get(DownloadJob, job_id)
        if job:
            job.telegram_status_message_id = message_id
            await session.commit()


def automatic_download_selection(
    platform: Platform,
    info: MediaInfo,
    upload_limit_bytes: int,
) -> tuple[MediaType, str] | None:
    if platform != Platform.INSTAGRAM:
        return None
    qualities = sorted(info.qualities, reverse=True)
    if not qualities:
        return MediaType.VIDEO, "best"
    sizes = info.quality_sizes.get("video", {})
    highest_quality = qualities[0]
    for quality in qualities:
        if not exceeds_upload_limit(sizes.get(str(quality)), upload_limit_bytes):
            selected = "best" if quality == highest_quality else str(quality)
            return MediaType.VIDEO, selected
    raise MediaProcessingError("too_large")


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "noma’lum"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@celery_app.task(name="media.analyze", ignore_result=True)
def analyze_media_task(job_id: str) -> None:
    run_async(analyze_job(uuid.UUID(job_id)))


@celery_app.task(name="media.download", bind=True, ignore_result=True, max_retries=None)
def download_media_task(task: object, job_id: str) -> None:
    should_retry = bool(run_async(download_job(uuid.UUID(job_id))))
    if should_retry:
        task.retry(countdown=get_settings().MEDIA_DEDUP_RETRY_SECONDS)


@celery_app.task(name="media.cleanup_stale", ignore_result=True)
def cleanup_stale_task() -> None:
    MediaService(get_settings()).cleanup_stale(21600)
