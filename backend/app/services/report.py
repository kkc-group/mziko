"""Weekly report and progress data for parents. Rendering lives in the bot."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import TBILISI, local_date, week_start
from app.models import Child, Session, Topic, Week, WeekStatus, Word, WordProgress
from app.services import coins
from app.services.learning import LEARNED_STAGE


@dataclass
class WeekReport:
    child: Child
    week: Week
    week_end: date
    days_studied: int
    learned: list[Word]
    lari: Decimal
    cap_reached: bool
    unpaid_past: list[Week]


def _week_bounds_utc(start: date) -> tuple[datetime, datetime]:
    begin = datetime.combine(start, time(0), tzinfo=TBILISI)
    return begin, begin + timedelta(days=7)


async def days_studied(db: AsyncSession, child_id: int, start: date) -> int:
    stmt = select(func.count(func.distinct(Session.study_date))).where(
        Session.child_id == child_id,
        Session.finished_at.is_not(None),
        Session.study_date >= start,
        Session.study_date < start + timedelta(days=7),
    )
    return (await db.execute(stmt)).scalar_one()


async def learned_in_week(db: AsyncSession, child_id: int, start: date) -> list[Word]:
    begin, end = _week_bounds_utc(start)
    stmt = (
        select(Word)
        .join(WordProgress, WordProgress.word_id == Word.id)
        .where(
            WordProgress.child_id == child_id,
            WordProgress.learned_at >= begin,
            WordProgress.learned_at < end,
        )
        .order_by(WordProgress.learned_at)
    )
    return list((await db.execute(stmt)).scalars())


async def unpaid_past_weeks(db: AsyncSession, child_id: int, before: date) -> list[Week]:
    stmt = (
        select(Week)
        .where(
            Week.child_id == child_id,
            Week.status == WeekStatus.open,
            Week.week_start < before,
            Week.coins > 0,
        )
        .order_by(Week.week_start)
    )
    return list((await db.execute(stmt)).scalars())


async def week_report(
    db: AsyncSession, child: Child, now: datetime, start: date | None = None
) -> WeekReport:
    """Report for the week containing `now` (or the week beginning at `start`)."""
    start = start or week_start(local_date(now))
    week = await coins.get_or_create_week(db, child.id, start)
    return WeekReport(
        child=child,
        week=week,
        week_end=start + timedelta(days=6),
        days_studied=await days_studied(db, child.id, start),
        learned=await learned_in_week(db, child.id, start),
        lari=coins.lari_for(week.coins, child.rate, child.cap_lari),
        cap_reached=week.coins >= coins.max_coins(child),
        unpaid_past=await unpaid_past_weeks(db, child.id, start),
    )


async def week_by_id(db: AsyncSession, week_id: int) -> Week | None:
    return await db.get(Week, week_id)


@dataclass
class TopicProgress:
    topic: Topic
    words: list[tuple[Word, WordProgress | None]]  # None: the child has never met the word

    @property
    def learned(self) -> int:
        return sum(1 for _, p in self.words if p is not None and p.stage >= LEARNED_STAGE)


async def progress_by_topic(db: AsyncSession, child: Child) -> list[TopicProgress]:
    topics = list((await db.execute(select(Topic).order_by(Topic.order))).scalars())
    words = list((await db.execute(select(Word).order_by(Word.topic_id, Word.order))).scalars())
    progress = {
        p.word_id: p
        for p in (
            await db.execute(select(WordProgress).where(WordProgress.child_id == child.id))
        ).scalars()
    }
    return [
        TopicProgress(topic=t, words=[(w, progress.get(w.id)) for w in words if w.topic_id == t.id])
        for t in topics
    ]


async def lessons_done(db: AsyncSession, child: Child) -> int:
    """Lessons the child played to the end, all time."""
    stmt = select(func.count()).where(
        Session.child_id == child.id, Session.finished_at.is_not(None)
    )
    return (await db.execute(stmt)).scalar_one()
