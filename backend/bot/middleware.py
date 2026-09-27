"""Bind the API client to the parent behind each update and turn API errors into replies."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.api import ApiError, ParentApi

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ParentApiMiddleware(BaseMiddleware):
    """The handler receives `api` acting for the sender.

    The API answers 403 for strangers: their updates are dropped silently, as
    before. 404 means "not yours or gone" and is shown as «Недоступно»; any
    other failure is logged and answered with a retry hint.
    """

    def __init__(self, api: ParentApi) -> None:
        self.api = api

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = event.from_user if isinstance(event, Message | CallbackQuery) else None
        if user is None:
            return None
        data["api"] = self.api.for_parent(user.id)
        try:
            return await handler(event, data)
        except ApiError as exc:
            if exc.status == 403:
                log.info("ignoring update from unknown telegram user %s", user.id)
                return None
            text = "Недоступно" if exc.status == 404 else "Не получилось, попробуйте позже"
            if exc.status != 404:
                log.error("api call failed for %s: %s", user.id, exc)
            if isinstance(event, CallbackQuery):
                await event.answer(text)
            elif isinstance(event, Message):
                await event.answer(text)
            return None
