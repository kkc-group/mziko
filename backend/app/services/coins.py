"""Weekly coin jar: crediting with the weekly cap, GEL conversion, payout."""

from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import week_start
from app.models import Child, CoinLedger, CoinReason, Week, WeekStatus

TENTH = Decimal("0.1")


def lari_for(coins: int, rate: int, cap_lari: int) -> Decimal:
    """GEL for `coins` at `rate` coins per GEL, floored to 0.1 and capped."""
    raw = (Decimal(coins) / Decimal(rate)).quantize(TENTH, rounding=ROUND_DOWN)
    return min(raw, Decimal(cap_lari))


def max_coins(child: Child) -> int:
    return child.rate * child.cap_lari


async def get_or_create_week(
    db: AsyncSession, child_id: int, day: date, *, for_update: bool = False
) -> Week:
    """The week row containing `day` (Tbilisi calendar), created on first use.

    With `for_update` the row is locked so concurrent credits serialise.
    """
    start = week_start(day)
    await db.execute(
        insert(Week).values(child_id=child_id, week_start=start).on_conflict_do_nothing()
    )
    stmt = select(Week).where(Week.child_id == child_id, Week.week_start == start)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one()


async def add_coins(
    db: AsyncSession,
    child: Child,
    week: Week,
    amount: int,
    reason: CoinReason,
    answer_id: int | None = None,
) -> int:
    """Credit up to `amount` coins, clipped by the weekly cap. Returns what was granted."""
    room = max_coins(child) - week.coins
    granted = max(0, min(amount, room))
    if granted == 0:
        return 0
    db.add(
        CoinLedger(
            child_id=child.id,
            week_id=week.id,
            answer_id=answer_id,
            amount=granted,
            reason=reason,
        )
    )
    week.coins += granted
    await db.flush()
    return granted


async def pay_week(db: AsyncSession, week: Week, child: Child, now: datetime) -> Week:
    """Close the week as paid. Idempotent: a paid week is returned unchanged."""
    if week.status is WeekStatus.paid:
        return week
    week.status = WeekStatus.paid
    week.paid_at = now
    week.lari_paid = lari_for(week.coins, child.rate, child.cap_lari)
    week.rate_snapshot = child.rate
    week.cap_snapshot = child.cap_lari
    await db.flush()
    return week
