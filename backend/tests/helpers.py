"""Small helpers shared by the service tests."""

import random
import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import TBILISI, local_date
from app.models import Child, Session, WordProgress
from app.schemas.lesson import AnswerIn, AnswerResult, Step
from app.services import learning, lessons

LONG_AGO = date(2026, 1, 5)


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """An aware UTC instant that is `day` `hour`:`minute` on the Tbilisi clock."""
    return datetime.combine(day, time(hour, minute), tzinfo=TBILISI).astimezone(UTC)


def steps_of(session: Session) -> list[Step]:
    return [Step.model_validate(s) for s in session.steps]


def quiz_steps(session: Session) -> list[tuple[int, Step]]:
    return [(i, s) for i, s in enumerate(steps_of(session)) if s.type != "intro"]


async def skip_to(db: AsyncSession, child: Child, topic_slug: str) -> int:
    """Make `topic_slug` reachable: every word of the lessons before it counts as learned long ago.

    Words already introduced are left alone, so their review state survives.
    Returns the number of the topic's first lesson.
    """
    path = await lessons.load_lessons(db)
    progress = await lessons.load_progress(db, child.id)
    first = next(lesson for lesson in path if lesson.topic.slug == topic_slug)
    for lesson in path[: first.number - 1]:
        for word in lesson.words:
            p = progress.get(word.id)
            if p is None:
                p = WordProgress(child_id=child.id, word_id=word.id)
                db.add(p)
            if not p.introduced:
                p.introduced = True
                p.introduced_on = LONG_AGO
                p.stage = learning.LEARNED_STAGE
                p.last_correct_date = LONG_AGO
                p.learned_at = at(LONG_AGO)
    await db.flush()
    return first.number


async def lesson_to_play(db: AsyncSession, child: Child, topic_slug: str, now: datetime) -> int:
    """The topic's lesson to play now: its first unfinished one, else its last (a replay)."""
    path = await lessons.load_lessons(db)
    today_topics = await lessons.load_today_topics(db, child.id, local_date(now))
    position = lessons.position(path, await lessons.load_progress(db, child.id), today_topics)
    topic = next(lesson.topic for lesson in path if lesson.topic.slug == topic_slug)
    state = position.lesson_of_topic(topic.id)
    assert state is not None
    return state.lesson.number


async def build_for_topic(
    db: AsyncSession,
    child: Child,
    topic_slug: str,
    now: datetime,
    rng: random.Random | None = None,
) -> Session | None:
    """Skip ahead to the topic and build a session for its lesson of the day."""
    await skip_to(db, child, topic_slug)
    number = await lesson_to_play(db, child, topic_slug, now)
    return await learning.build_session(db, child, number, now, rng)


async def answer_correctly(
    db: AsyncSession,
    child: Child,
    session: Session,
    step_index: int,
    now: datetime,
    attempt: int = 1,
) -> AnswerResult:
    step = steps_of(session)[step_index]
    payload = AnswerIn(
        step_index=step_index,
        word_slug=step.word.slug,
        attempt=attempt,
        client_answer_id=uuid.uuid4(),
    )
    return await learning.submit_answer(db, child, session.id, payload, now)


async def play_day(
    db: AsyncSession, child: Child, topic_slug: str, now: datetime
) -> Session | None:
    """Build a session for the topic and answer every quiz step correctly on the first try."""
    session = await build_for_topic(db, child, topic_slug, now)
    if session is None:
        return None
    for index, _ in quiz_steps(session):
        await answer_correctly(db, child, session, index, now)
    await learning.finish_session(db, child, session.id, now)
    await db.commit()
    return session
