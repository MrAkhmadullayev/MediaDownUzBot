from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from app.config import Settings


def create_bot(settings: Settings) -> Bot:
    api = TelegramAPIServer.from_base(
        settings.TELEGRAM_API_BASE_URL,
        is_local=settings.TELEGRAM_LOCAL_MODE,
    )
    return Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=AiohttpSession(api=api, timeout=settings.TELEGRAM_UPLOAD_TIMEOUT_SECONDS),
    )
