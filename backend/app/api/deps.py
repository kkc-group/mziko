"""FastAPI dependencies: database session, clock, authenticated child."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.db import get_sessionmaker
from app.models import Child
from app.services import pairing


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request, committed when the endpoint returns normally."""
    async with get_sessionmaker()() as session:
        yield session
        await session.commit()


def get_now() -> datetime:
    return clock.now()


Db = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]


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
