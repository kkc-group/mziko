"""Read-only overview of every parent for the back office. Rendering lives there."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import week_start
from app.models import Answer, Child, Device, Parent, Session, Week, WordProgress
from app.services import report
from app.services.learning import LEARNED_STAGE
from app.services.report import TopicProgress

# The activity calendar and the first-try share cover this many days back from today.
CALENDAR_DAYS = 28
WEEKS_SHOWN = 6


@dataclass
class ChildOverview:
    child: Child
    learned_words: int
    # Tbilisi day of the child's most recent lesson, started or finished; None = never played.
    last_study_date: date | None
    # None = no coins earned that week (the row is only created by the first answer).
    this_week: Week | None
    last_week: Week | None


@dataclass
class ParentOverview:
    parent: Parent
    children: list[ChildOverview]

    @property
    def last_study_date(self) -> date | None:
        dates = [c.last_study_date for c in self.children if c.last_study_date is not None]
        return max(dates) if dates else None


async def parents_overview(db: AsyncSession, today: date) -> list[ParentOverview]:
    """Every parent with a per-child summary, newest parent first. Four queries in all."""
    parents = list(
        (
            await db.execute(
                select(Parent)
                .options(selectinload(Parent.children))
                .order_by(Parent.created_at.desc(), Parent.id.desc())
            )
        ).scalars()
    )
    learned = dict(
        (
            await db.execute(
                select(WordProgress.child_id, func.count())
                .where(WordProgress.stage >= LEARNED_STAGE)
                .group_by(WordProgress.child_id)
            )
        ).all()
    )
    last_study = dict(
        (
            await db.execute(
                select(Session.child_id, func.max(Session.study_date)).group_by(Session.child_id)
            )
        ).all()
    )
    this_start = week_start(today)
    last_start = this_start - timedelta(days=7)
    weeks = {
        (w.child_id, w.week_start): w
        for w in (
            await db.execute(select(Week).where(Week.week_start.in_([this_start, last_start])))
        ).scalars()
    }
    return [
        ParentOverview(
            parent=p,
            children=[
                ChildOverview(
                    child=c,
                    learned_words=learned.get(c.id, 0),
                    last_study_date=last_study.get(c.id),
                    this_week=weeks.get((c.id, this_start)),
                    last_week=weeks.get((c.id, last_start)),
                )
                for c in sorted(p.children, key=lambda c: c.id)
            ],
        )
        for p in parents
    ]


@dataclass
class StudyDay:
    day: date
    finished: bool  # at least one lesson of that day was played to the end


@dataclass
class ChildCard:
    child: Child
    topics: list[TopicProgress]
    # Word ids the child has seen at least once: a topic with any of them is "in progress".
    introduced: set[int]
    study_days: list[StudyDay]
    # Share of first attempts answered correctly over the calendar window; None = no answers.
    first_try_pct: int | None
    weeks: list[Week]
    devices: list[Device]

    @property
    def learned_words(self) -> int:
        return sum(t.learned for t in self.topics)


@dataclass
class ParentCard:
    parent: Parent
    children: list[ChildCard]


async def _study_days(db: AsyncSession, child_id: int, since: date) -> list[StudyDay]:
    stmt = (
        select(Session.study_date, func.bool_or(Session.finished_at.is_not(None)))
        .where(Session.child_id == child_id, Session.study_date >= since)
        .group_by(Session.study_date)
        .order_by(Session.study_date)
    )
    return [StudyDay(day, bool(finished)) for day, finished in (await db.execute(stmt)).all()]


async def _first_try_pct(db: AsyncSession, child_id: int, since: date) -> int | None:
    stmt = (
        select(func.count(), func.count().filter(Answer.correct))
        .join(Session, Session.id == Answer.session_id)
        .where(Session.child_id == child_id, Session.study_date >= since, Answer.attempt == 1)
    )
    total, correct = (await db.execute(stmt)).one()
    return round(100 * correct / total) if total else None


async def _child_card(db: AsyncSession, child: Child, today: date) -> ChildCard:
    since = today - timedelta(days=CALENDAR_DAYS - 1)
    introduced = set(
        (
            await db.execute(
                select(WordProgress.word_id).where(
                    WordProgress.child_id == child.id, WordProgress.introduced
                )
            )
        ).scalars()
    )
    weeks = list(
        (
            await db.execute(
                select(Week)
                .where(Week.child_id == child.id)
                .order_by(Week.week_start.desc())
                .limit(WEEKS_SHOWN)
            )
        ).scalars()
    )
    devices = list(
        (
            await db.execute(
                select(Device).where(Device.child_id == child.id).order_by(Device.created_at)
            )
        ).scalars()
    )
    return ChildCard(
        child=child,
        topics=await report.progress_by_topic(db, child),
        introduced=introduced,
        study_days=await _study_days(db, child.id, since),
        first_try_pct=await _first_try_pct(db, child.id, since),
        weeks=weeks,
        devices=devices,
    )


async def parent_card(db: AsyncSession, parent_id: int, today: date) -> ParentCard | None:
    """One parent with everything the back office shows per child; None when unknown."""
    parent = (
        await db.execute(
            select(Parent).options(selectinload(Parent.children)).where(Parent.id == parent_id)
        )
    ).scalar_one_or_none()
    if parent is None:
        return None
    children = sorted(parent.children, key=lambda c: c.id)
    return ParentCard(parent=parent, children=[await _child_card(db, c, today) for c in children])
