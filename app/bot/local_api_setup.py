import asyncio

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    session = AiohttpSession(timeout=60)
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), session=session)
    try:
        logged_out = await bot.log_out()
        if not logged_out:
            raise RuntimeError("Telegram bulut Bot API sessiyasidan chiqib bo‘lmadi")
        print("Telegram bulut Bot API sessiyasi yopildi. Lokal Bot API ishga tushirishga tayyor.")
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
