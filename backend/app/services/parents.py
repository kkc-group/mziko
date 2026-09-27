"""Parents, their children and child settings (managed from the Telegram bot)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Child, Parent, parent_children

RATE_OPTIONS = (5, 10, 15, 20, 30)
CAP_OPTIONS = (5, 10, 15, 20, 30)


async def ensure_admin_parents(db: AsyncSession, telegram_ids: Iterable[int]) -> None:
    """Make sure every configured admin exists as a parent (idempotent)."""
    ids = list(telegram_ids)
    if not ids:
        return
    await db.execute(
        insert(Parent).values([{"telegram_id": tid} for tid in ids]).on_conflict_do_nothing()
    )
    await db.flush()


async def get_parent(db: AsyncSession, telegram_id: int) -> Parent | None:
    stmt = select(Parent).where(Parent.telegram_id == telegram_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def children_of(db: AsyncSession, parent: Parent) -> list[Child]:
    stmt = (
        select(Child)
        .join(parent_children)
        .where(parent_children.c.parent_id == parent.id)
        .order_by(Child.id)
    )
    return list((await db.execute(stmt)).scalars())


async def child_of_parent(db: AsyncSession, parent: Parent, child_id: int) -> Child | None:
    """The child only if this parent is linked to it: the bot's access boundary."""
    stmt = (
        select(Child)
        .join(parent_children)
        .where(parent_children.c.parent_id == parent.id, Child.id == child_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def parents_of(db: AsyncSession, child_id: int) -> list[Parent]:
    stmt = select(Parent).join(parent_children).where(parent_children.c.child_id == child_id)
    return list((await db.execute(stmt)).scalars())


async def all_children(db: AsyncSession) -> list[Child]:
    stmt = select(Child).options(selectinload(Child.parents)).order_by(Child.id)
    return list((await db.execute(stmt)).scalars())


async def create_child(db: AsyncSession, parent: Parent, name: str) -> Child:
    child = Child(name=name.strip())
    db.add(child)
    await db.flush()
    await db.execute(insert(parent_children).values(parent_id=parent.id, child_id=child.id))
    await db.flush()
    return child


async def update_settings(
    db: AsyncSession,
    child: Child,
    *,
    rate: int | None = None,
    cap_lari: int | None = None,
    show_hint: bool | None = None,
) -> Child:
    if rate is not None:
        if rate not in RATE_OPTIONS:
            raise ValueError(f"rate must be one of {RATE_OPTIONS}")
        child.rate = rate
    if cap_lari is not None:
        if cap_lari not in CAP_OPTIONS:
            raise ValueError(f"cap must be one of {CAP_OPTIONS}")
        child.cap_lari = cap_lari
    if show_hint is not None:
        child.show_hint = show_hint
    await db.flush()
    return child
