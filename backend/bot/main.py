"""Telegram bot process: `python -m bot.main`. Talks to the API only, never to the database."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.core.config import get_settings
from bot.api import ParentApi, make_client
from bot.handlers import router
from bot.keyboards import cabinet_url
from bot.middleware import ParentApiMiddleware
from bot.scheduler import setup_scheduler


async def run() -> None:
    settings = get_settings()
    if not settings.bot_token:
        sys.exit("BOT_TOKEN is not set")
    if not settings.bot_api_token:
        sys.exit("BOT_API_TOKEN is not set")

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    async with make_client(settings.api_url, settings.bot_api_token) as client:
        api = ParentApi(client)
        dp.message.middleware(ParentApiMiddleware(api))
        dp.callback_query.middleware(ParentApiMiddleware(api))
        dp.include_router(router)

        # The persistent "Кабинет" button next to the message box, in every private chat.
        url = cabinet_url(settings.public_url)
        if url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Кабинет", web_app=WebAppInfo(url=url))
            )
        else:
            logging.getLogger(__name__).info("PUBLIC_URL is not https: no cabinet button")

        scheduler = setup_scheduler(bot, api, settings.timezone)
        scheduler.start()
        try:
            await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
        finally:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(run())
