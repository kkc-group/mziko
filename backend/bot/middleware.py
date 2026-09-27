"""Per-update database session and the parent-only gate."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.db import get_sessionmaker
from app.services import parents

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ParentSessionMiddleware(BaseMiddleware):
    """Open a DB session, resolve the parent; silently drop updates from strangers.

    The handler receives `db` and `parent`; the session is committed after it.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = event.from_user if isinstance(event, Message | CallbackQuery) else None
        if user is None:
            return None
        async with get_sessionmaker()() as db:
            parent = await parents.get_parent(db, user.id)
            if parent is None:
                log.info("ignoring update from unknown telegram user %s", user.id)
                return None
            data["db"] = db
            data["parent"] = parent
            result = await handler(event, data)
            await db.commit()
            return result
