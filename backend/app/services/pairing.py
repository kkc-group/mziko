"""Device tokens: long-lived bearer keys a device gets after a login (see login_codes).

Only a SHA-256 hash of the device token is stored; the raw token is shown once.
"""

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Device
from app.services.errors import NotFound


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def authenticate_device(db: AsyncSession, raw: str, now: datetime) -> Child | None:
    stmt = select(Device).where(Device.token_hash == hash_token(raw), Device.revoked_at.is_(None))
    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is None:
        return None
    device.last_seen_at = now
    return await db.get_one(Child, device.child_id)


async def active_devices(db: AsyncSession, child_id: int) -> list[Device]:
    stmt = (
        select(Device)
        .where(Device.child_id == child_id, Device.revoked_at.is_(None))
        .order_by(Device.created_at)
    )
    return list((await db.execute(stmt)).scalars())


async def revoke_device(db: AsyncSession, device_id: int, now: datetime) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise NotFound(f"device {device_id}")
    if device.revoked_at is None:
        device.revoked_at = now
        await db.flush()
    return device
