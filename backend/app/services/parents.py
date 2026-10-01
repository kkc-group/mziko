"""Parents, their children and child settings (managed from the Telegram bot)."""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Child, CoinLedger, Parent, Session, Week, WordProgress, parent_children
from app.schemas.parent import CAP_OPTIONS, RATE_OPTIONS
from app.services.login_codes import normalize_word


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


async def register(db: AsyncSession, telegram_id: int, name: str) -> Parent:
    """The first step of the bot's wizard: create the parent, or rename an existing one."""
    parent = await get_parent(db, telegram_id)
    if parent is None:
        parent = Parent(telegram_id=telegram_id)
        db.add(parent)
    parent.name = name.strip()
    await db.flush()
    return parent


async def set_photo(db: AsyncSession, parent: Parent, photo_url: str) -> None:
    """Remember the profile photo the cabinet saw on entry; a saved one is only ever replaced."""
    parent.photo_url = photo_url
    await db.flush()


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


async def attach_child_by_code(db: AsyncSession, parent: Parent, code: str) -> Child | None:
    """Link an existing child by its login code WORD-1234; knowing the code is the right.

    Idempotent for a parent already linked. None when no child has that code.
    """
    word, _, pin = code.strip().partition("-")
    stmt = select(Child).where(Child.code_word == normalize_word(word), Child.code_pin == pin)
    child = (await db.execute(stmt)).scalar_one_or_none()
    if child is None:
        return None
    await db.execute(
        insert(parent_children)
        .values(parent_id=parent.id, child_id=child.id)
        .on_conflict_do_nothing()
    )
    await db.flush()
    return child


async def detach_child(db: AsyncSession, parent: Parent, child: Child) -> None:
    """Drop the link only: the child, its progress, code and devices stay for a re-attach."""
    await db.execute(
        delete(parent_children).where(
            parent_children.c.parent_id == parent.id, parent_children.c.child_id == child.id
        )
    )
    await db.flush()


async def reset_progress(db: AsyncSession, child: Child) -> None:
    """Forget everything the child has learned and earned; settings, code and devices stay."""
    await db.execute(delete(CoinLedger).where(CoinLedger.child_id == child.id))
    await db.execute(delete(Week).where(Week.child_id == child.id))
    await db.execute(delete(Session).where(Session.child_id == child.id))  # answers cascade
    await db.execute(delete(WordProgress).where(WordProgress.child_id == child.id))
    await db.flush()


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
