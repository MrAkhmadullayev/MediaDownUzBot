import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from redis.asyncio import Redis

from app.bot.client import create_bot
from app.bot.middleware import DatabaseSessionMiddleware
from app.bot.router import router
from app.config import get_settings
from app.database import Database
from app.logging import configure_logging
from app.services.crypto import FieldCipher
from app.tasks.celery_app import celery_app


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    database = Database(settings.DATABASE_URL)
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis, state_ttl=900, data_ttl=900)
    dispatcher = Dispatcher(storage=storage)
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware(database))
    dispatcher.include_router(router)
    bot = create_bot(settings)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Botni ishga tushirish"),
            BotCommand(command="help", description="Foydalanish bo‘yicha yordam"),
            BotCommand(command="cancel", description="Faol vazifani bekor qilish"),
        ]
    )
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            settings=settings,
            cipher=FieldCipher(settings.FIELD_ENCRYPTION_KEY.get_secret_value()),
            redis=redis,
            task_queue=celery_app,
        )
    finally:
        await storage.close()
        await database.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
