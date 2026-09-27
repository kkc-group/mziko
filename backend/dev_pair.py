"""Dev helper: create a parent + child (if missing) and print a fresh pairing code.

Usage: uv run python scripts_dev_pair.py [child name]
"""

import asyncio
import sys

from sqlalchemy import select

from app.core import clock
from app.core.db import get_sessionmaker
from app.models import Child, Parent
from app.services import pairing, parents


async def main(name: str) -> None:
    async with get_sessionmaker()() as db:
        parent = (await db.execute(select(Parent).where(Parent.telegram_id == 1))).scalar_one_or_none()
        if parent is None:
            parent = Parent(telegram_id=1, name="dev")
            db.add(parent)
            await db.flush()
        children = await parents.children_of(db, parent)
        child: Child = children[0] if children else await parents.create_child(db, parent, name)
        code = await pairing.create_pair_code(db, parent, child, clock.now())
        await db.commit()
        print(code.code)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Сандро"))
