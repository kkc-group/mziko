"""Telegram bot process: `python -m bot.main`."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services import parents
from bot.handlers import router
from bot.middleware import ParentSessionMiddleware
from bot.scheduler import setup_scheduler


async def run() -> None:
    settings = get_settings()
    if not settings.bot_token:
        sys.exit("BOT_TOKEN is not set")

    async with get_sessionmaker()() as db:
        await parents.ensure_admin_parents(db, settings.admin_telegram_ids)
        await db.commit()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(ParentSessionMiddleware())
    dp.callback_query.middleware(ParentSessionMiddleware())
    dp.include_router(router)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
