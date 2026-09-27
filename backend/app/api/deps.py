"""FastAPI dependencies: database session, clock, authenticated child or parent."""

import secrets
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import Child, Parent
from app.services import pairing, parents


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request, committed when the endpoint returns normally."""
    async with get_sessionmaker()() as session:
        yield session
        await session.commit()


def get_now() -> datetime:
    return clock.now()


def client_ip(request: Request) -> str:
    """The caller's address; behind Caddy uvicorn must trust X-Forwarded-For (see compose)."""
    return request.client.host if request.client else "unknown"


Db = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]
ClientIp = Annotated[str, Depends(client_ip)]


async def current_child(
    db: Db, now: Now, authorization: Annotated[str | None, Header()] = None
) -> Child:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "device token required")
    child = await pairing.authenticate_device(db, token, now)
    if child is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "device not paired")
    return child


CurrentChild = Annotated[Child, Depends(current_child)]


def bot_service(authorization: Annotated[str | None, Header()] = None) -> None:
    """The Telegram bot authenticates with the shared BOT_API_TOKEN."""
    expected = get_settings().bot_api_token
    scheme, _, token = (authorization or "").partition(" ")
    if not expected or scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bot token required")


async def current_parent(
    db: Db,
    _: Annotated[None, Depends(bot_service)],
    x_telegram_id: Annotated[int | None, Header()] = None,
) -> Parent:
    """The parent the bot acts for; strangers get 403 and the bot stays silent to them."""
    if x_telegram_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Telegram-Id header required")
    parent = await parents.get_parent(db, x_telegram_id)
    if parent is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unknown parent")
    return parent


BotService = Annotated[None, Depends(bot_service)]
CurrentParent = Annotated[Parent, Depends(current_parent)]
