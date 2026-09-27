"""Dev helper for testing without Telegram.

    uv run python dev_pair.py            # one-time pairing code, as the bot would give
    uv run python dev_pair.py token      # shared device token that works in any browser

Both create a dev parent (telegram id 1) and a child "Сандро" on first use.
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.db import get_sessionmaker
from app.models import Child, Device, Parent
from app.services import pairing, parents

SHARED_TOKEN = "dev-shared-token"
WEB_URL = "http://localhost"


async def dev_child(db: AsyncSession) -> tuple[Parent, Child]:
    parent = (await db.execute(select(Parent).where(Parent.telegram_id == 1))).scalar_one_or_none()
    if parent is None:
        parent = Parent(telegram_id=1, name="dev")
        db.add(parent)
        await db.flush()
    children = await parents.children_of(db, parent)
    child = children[0] if children else await parents.create_child(db, parent, "Сандро")
    return parent, child


async def main(mode: str) -> None:
    async with get_sessionmaker()() as db:
        parent, child = await dev_child(db)
        if mode == "token":
            token_hash = pairing.hash_token(SHARED_TOKEN)
            device = (
                await db.execute(select(Device).where(Device.token_hash == token_hash))
            ).scalar_one_or_none()
            if device is None:
                db.add(Device(child_id=child.id, token_hash=token_hash, name="shared dev"))
            elif device.revoked_at is not None:
                device.revoked_at = None
            print(f"{WEB_URL}/?token={SHARED_TOKEN}")
        else:
            code = await pairing.create_pair_code(db, parent, child, clock.now())
            print(f"{WEB_URL}/pair/{code.code}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "code"))
