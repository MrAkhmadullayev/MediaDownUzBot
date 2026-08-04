import asyncio
import html
import logging
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import update

from app.bot.client import create_bot
from app.bot.keyboards import support_ticket_keyboard
from app.config import get_settings
from app.database import Database
from app.enums import BroadcastStatus, DeliveryStatus, SupportSender
from app.models import Broadcast, BroadcastDelivery, SupportMessage
from app.repositories import BroadcastRepository, SupportRepository
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


async def send_with_retry[ResultT](send_call: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await send_call()
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        return await send_call()


async def notify_admins(message_id: uuid.UUID) -> None:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings)
    try:
        async with database.session_factory() as session:
            message = await session.get(SupportMessage, message_id)
            if message is None or message.sender != SupportSender.USER:
                return
            ticket = await SupportRepository.get_details(session, message.ticket_id)
            if ticket is None:
                return
            user = ticket.user
            username = f"@{user.username}" if user.username else "username yo‘q"
            name = " ".join(part for part in (user.first_name, user.last_name) if part)
            body = (
                "💬 <b>Yangi murojaat</b>\n\n"
                f"👤 {html.escape(name)} · {html.escape(username)}\n"
                f"🆔 <code>{user.telegram_id}</code>\n"
                f"🎫 <code>#{str(ticket.id)[:8]}</code>\n\n"
                f"{html.escape(message.body[:2000])}"
            )
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Murojaatni ochish",
                            url=f"{settings.ADMIN_BASE_URL.rstrip('/')}/admin/support/{ticket.id}",
                        )
                    ]
                ]
            )
        for admin_id in settings.ADMIN_TELEGRAM_IDS:
            try:
                await send_with_retry(
                    lambda admin_id=admin_id: bot.send_message(admin_id, body, reply_markup=markup)
                )
            except Exception as exc:
                logger.warning(
                    "support_admin_notification_failed",
                    extra={"admin_id": admin_id, "error_type": type(exc).__name__},
                )
    finally:
        await bot.session.close()
        await database.close()


async def deliver_support_message(message_id: uuid.UUID) -> None:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings)
    try:
        async with database.session_factory() as session:
            message = await session.get(SupportMessage, message_id, with_for_update=True)
            if (
                message is None
                or message.sender != SupportSender.ADMIN
                or message.delivery_status not in {DeliveryStatus.PENDING, DeliveryStatus.FAILED}
            ):
                return
            ticket = await SupportRepository.get_details(session, message.ticket_id)
            if ticket is None:
                message.delivery_status = DeliveryStatus.FAILED
                message.error_detail = "SupportTicketNotFound"
                await session.commit()
                return
            message.delivery_status = DeliveryStatus.SENDING
            message.error_detail = None
            await session.commit()
            try:
                sent = await send_with_retry(
                    lambda: bot.send_message(
                        ticket.user_id,
                        "💬 <b>Qo‘llab-quvvatlash javobi</b>\n\n"
                        f"🎫 Murojaat: <code>#{str(ticket.id)[:8]}</code>\n\n"
                        f"{html.escape(message.body)}",
                        reply_markup=support_ticket_keyboard(ticket.id),
                    )
                )
            except TelegramForbiddenError as exc:
                ticket.user.is_active = False
                message.delivery_status = DeliveryStatus.FAILED
                message.error_detail = type(exc).__name__[:500]
                await session.commit()
                return
            except Exception as exc:
                message.delivery_status = DeliveryStatus.FAILED
                message.error_detail = type(exc).__name__[:500]
                await session.commit()
                raise
            message.delivery_status = DeliveryStatus.SENT
            message.telegram_message_id = sent.message_id
            message.sent_at = datetime.now(UTC)
            await session.commit()
    finally:
        await bot.session.close()
        await database.close()


async def deliver_broadcast(broadcast_id: uuid.UUID) -> None:
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings)
    try:
        async with database.session_factory() as session:
            claimed = await session.get(Broadcast, broadcast_id, with_for_update=True)
            if claimed is None or claimed.status not in {
                BroadcastStatus.PENDING,
                BroadcastStatus.PARTIAL,
                BroadcastStatus.FAILED,
            }:
                return
            claimed.status = BroadcastStatus.PROCESSING
            claimed.started_at = datetime.now(UTC)
            claimed.completed_at = None
            await session.commit()
            broadcast = await BroadcastRepository.get_with_deliveries(session, broadcast_id)
            if broadcast is None:
                return
            for delivery in broadcast.deliveries:
                if delivery.status == DeliveryStatus.SENT:
                    continue
                delivery.status = DeliveryStatus.SENDING
                delivery.error_detail = None
                await session.commit()
                try:
                    sent = await send_with_retry(
                        lambda delivery=delivery: bot.send_message(
                            delivery.user_id,
                            f"📣 <b>Media Yukla xabari</b>\n\n{html.escape(broadcast.body)}",
                        )
                    )
                except TelegramForbiddenError as exc:
                    delivery.user.is_active = False
                    delivery.status = DeliveryStatus.FAILED
                    delivery.error_detail = type(exc).__name__
                except Exception as exc:
                    delivery.status = DeliveryStatus.FAILED
                    delivery.error_detail = type(exc).__name__[:500]
                else:
                    delivery.status = DeliveryStatus.SENT
                    delivery.telegram_message_id = sent.message_id
                    delivery.sent_at = datetime.now(UTC)
                await session.commit()
                await asyncio.sleep(0.055)
            await BroadcastRepository.update_totals(session, broadcast)
            if broadcast.failed_count == 0:
                broadcast.status = BroadcastStatus.COMPLETED
            elif broadcast.sent_count:
                broadcast.status = BroadcastStatus.PARTIAL
            else:
                broadcast.status = BroadcastStatus.FAILED
            broadcast.completed_at = datetime.now(UTC)
            await session.commit()
    except Exception as exc:
        async with database.session_factory() as recovery_session:
            failed = await recovery_session.get(Broadcast, broadcast_id, with_for_update=True)
            if failed is not None and failed.status == BroadcastStatus.PROCESSING:
                await recovery_session.execute(
                    update(BroadcastDelivery)
                    .where(
                        BroadcastDelivery.broadcast_id == broadcast_id,
                        BroadcastDelivery.status == DeliveryStatus.SENDING,
                    )
                    .values(
                        status=DeliveryStatus.FAILED,
                        error_detail=type(exc).__name__[:500],
                    )
                )
                await BroadcastRepository.update_totals(recovery_session, failed)
                failed.status = (
                    BroadcastStatus.PARTIAL if failed.sent_count else BroadcastStatus.FAILED
                )
                failed.completed_at = datetime.now(UTC)
                await recovery_session.commit()
        raise
    finally:
        await bot.session.close()
        await database.close()


@celery_app.task(name="notifications.support.notify_admins", ignore_result=True)
def notify_admins_task(message_id: str) -> None:
    run_async(notify_admins(uuid.UUID(message_id)))


@celery_app.task(
    name="notifications.support.deliver_reply",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def deliver_support_message_task(message_id: str) -> None:
    run_async(deliver_support_message(uuid.UUID(message_id)))


@celery_app.task(
    name="notifications.broadcast.deliver",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def deliver_broadcast_task(broadcast_id: str) -> None:
    run_async(deliver_broadcast(uuid.UUID(broadcast_id)))
