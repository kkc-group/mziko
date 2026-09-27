from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, CoinLedger, CoinReason, WeekStatus
from app.services import coins
from tests.helpers import at


def test_lari_for_floors_to_tenth_and_caps() -> None:
    assert coins.lari_for(25, 10, 15) == Decimal("2.5")
    assert coins.lari_for(27, 10, 15) == Decimal("2.7")
    assert coins.lari_for(51, 20, 15) == Decimal("2.5")  # 2.55 floors, not rounds
    assert coins.lari_for(9, 10, 15) == Decimal("0.9")
    assert coins.lari_for(0, 10, 15) == Decimal("0.0")
    assert coins.lari_for(999, 10, 15) == Decimal("15")


async def test_add_coins_respects_weekly_cap(db: AsyncSession, child: Child) -> None:
    child.rate, child.cap_lari = 1, 3  # max 3 coins per week
    week = await coins.get_or_create_week(db, child.id, date(2026, 9, 23))

    assert await coins.add_coins(db, child, week, 2, CoinReason.answer) == 2
    assert await coins.add_coins(db, child, week, 5, CoinReason.word_learned) == 1
    assert await coins.add_coins(db, child, week, 1, CoinReason.answer) == 0
    assert week.coins == 3

    ledger = (
        await db.execute(select(CoinLedger.amount).where(CoinLedger.week_id == week.id))
    ).scalars()
    assert sorted(ledger) == [1, 2]  # no zero rows written


async def test_week_row_is_shared_within_week_and_split_across_weeks(
    db: AsyncSession, child: Child
) -> None:
    monday = await coins.get_or_create_week(db, child.id, date(2026, 9, 21))
    sunday = await coins.get_or_create_week(db, child.id, date(2026, 9, 27))
    next_monday = await coins.get_or_create_week(db, child.id, date(2026, 9, 28))
    assert monday.id == sunday.id
    assert next_monday.id != monday.id
    assert next_monday.week_start == date(2026, 9, 28)


async def test_pay_week_is_idempotent_and_snapshots_settings(
    db: AsyncSession, child: Child
) -> None:
    child.rate, child.cap_lari = 10, 15
    week = await coins.get_or_create_week(db, child.id, date(2026, 9, 23))
    await coins.add_coins(db, child, week, 37, CoinReason.answer)

    first_paid_at = at(date(2026, 9, 27), 20)
    await coins.pay_week(db, week, child, first_paid_at)
    assert week.status is WeekStatus.paid
    assert week.lari_paid == Decimal("3.7")
    assert (week.rate_snapshot, week.cap_snapshot) == (10, 15)

    child.rate = 5  # settings change after payout must not alter the closed week
    await coins.pay_week(db, week, child, at(date(2026, 9, 27), 21))
    assert week.paid_at == first_paid_at
    assert week.lari_paid == Decimal("3.7")
    assert week.rate_snapshot == 10

    # A paid week no longer accepts coins in practice because the app credits the
    # *current* week; the service itself still clips by cap only.
