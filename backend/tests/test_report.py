from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, CoinReason, Parent
from app.services import coins, parents, report
from bot import texts
from tests.helpers import at, play_day

MON = date(2026, 9, 21)
SUN = date(2026, 9, 27)


async def test_week_report_counts_days_words_and_cap(db: AsyncSession, child: Child) -> None:
    child.rate, child.cap_lari = 1, 5  # cap at 5 coins so it is reached quickly
    for day in (21, 22, 23):
        await play_day(db, child, "colors", at(date(2026, 9, day)))

    r = await report.week_report(db, child, at(SUN, 20))
    assert r.days_studied == 3
    assert {w.slug for w in r.learned} == {"red", "blue", "green"}
    assert (r.week.coins, r.cap_reached, str(r.lari)) == (5, True, "5.0")
    assert r.unpaid_past == []

    text = texts.report_text(r)
    assert "Неделя 21.09–27.09" in text
    assert "Занимался 3 из 7 дней" in text
    assert "Выучено слов: 3 (" in text
    assert all(w in text for w in ("წითელი", "ლურჯი", "მწვანე"))
    assert "5,0 ₾" in text and "достигнут лимит" in text
    assert "Выплачено" in text


async def test_unpaid_previous_week_is_listed_until_paid(db: AsyncSession, child: Child) -> None:
    old = await coins.get_or_create_week(db, child.id, date(2026, 9, 14))
    await coins.add_coins(db, child, old, 21, CoinReason.answer)
    empty = await coins.get_or_create_week(db, child.id, date(2026, 9, 7))
    assert empty.coins == 0

    r = await report.week_report(db, child, at(SUN, 20))
    assert [w.id for w in r.unpaid_past] == [old.id]  # empty week is not "to pay"
    assert "14.09–20.09 — 2,1 ₾" in texts.report_text(r)

    await coins.pay_week(db, old, child, at(SUN, 20, 5))
    r = await report.week_report(db, child, at(SUN, 20, 6))
    assert r.unpaid_past == []


async def test_learned_words_belong_to_the_week_of_tbilisi_time(
    db: AsyncSession, child: Child
) -> None:
    for day in (25, 26):
        await play_day(db, child, "colors", at(date(2026, 9, day)))
    # Third correct day at 23:50 Sunday Tbilisi: learned in this week, not the next.
    await play_day(db, child, "colors", at(SUN, 23, 50))
    this_week = await report.learned_in_week(db, child.id, MON)
    next_week = await report.learned_in_week(db, child.id, date(2026, 9, 28))
    assert {w.slug for w in this_week} == {"red", "blue", "green"}
    assert next_week == []


async def test_parent_child_access_boundary(db: AsyncSession, child: Child) -> None:
    await parents.ensure_admin_parents(db, [777_001, 777_002])
    await parents.ensure_admin_parents(db, [777_001])  # idempotent
    mine = await parents.get_parent(db, 777_001)
    other = await parents.get_parent(db, 777_002)
    assert mine is not None and other is not None

    db.add(Parent(telegram_id=777_003))
    await db.flush()
    created = await parents.create_child(db, mine, " Нино ")
    assert created.name == "Нино"
    assert [c.id for c in await parents.children_of(db, mine)] == [created.id]
    assert await parents.child_of_parent(db, mine, created.id) is not None
    assert await parents.child_of_parent(db, other, created.id) is None
    assert await parents.child_of_parent(db, other, child.id) is None


async def test_progress_text_shows_dots(db: AsyncSession, child: Child) -> None:
    await play_day(db, child, "colors", at(MON))
    text = texts.progress_text(child, await report.progress_by_topic(db, child))
    assert "🎨 <b>Цвета</b> — 0 из 10" in text
    assert "●○○ წითელი · красный" in text
    assert "○○○ ლურჯი" not in text and "●○○ ლურჯი · синий" in text
    assert "○○○ ძაღლი · собака" in text
