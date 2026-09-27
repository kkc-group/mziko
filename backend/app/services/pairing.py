"""Device pairing: one-time codes issued by a parent, long-lived device tokens.

Only a SHA-256 hash of the device token is stored; the raw token is shown once.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Device, PairCode, Parent
from app.services.errors import NotFound

PAIR_CODE_TTL = timedelta(minutes=15)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_pair_code(
    db: AsyncSession, parent: Parent, child: Child, now: datetime
) -> PairCode:
    code = PairCode(
        code=secrets.token_urlsafe(9),
        child_id=child.id,
        parent_id=parent.id,
        expires_at=now + PAIR_CODE_TTL,
    )
    db.add(code)
    await db.flush()
    return code


async def redeem_pair_code(
    db: AsyncSession, code: str, now: datetime, device_name: str | None = None
) -> tuple[str, Child]:
    """Exchange a valid code for a new device token. Returns (raw_token, child)."""
    stmt = select(PairCode).where(PairCode.code == code).with_for_update()
    pair = (await db.execute(stmt)).scalar_one_or_none()
    if pair is None or pair.used_at is not None or pair.expires_at <= now:
        raise NotFound("pair code")
    pair.used_at = now
    raw = secrets.token_urlsafe(32)
    db.add(Device(child_id=pair.child_id, token_hash=hash_token(raw), name=device_name))
    await db.flush()
    child = await db.get_one(Child, pair.child_id)
    return raw, child


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
