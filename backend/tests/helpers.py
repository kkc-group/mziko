"""Small helpers shared by the service tests."""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import TBILISI
from app.models import Child, Session
from app.schemas.lesson import AnswerIn, AnswerResult, Step
from app.services import learning


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """An aware UTC instant that is `day` `hour`:`minute` on the Tbilisi clock."""
    return datetime.combine(day, time(hour, minute), tzinfo=TBILISI).astimezone(UTC)


def steps_of(session: Session) -> list[Step]:
    return [Step.model_validate(s) for s in session.steps]


def quiz_steps(session: Session) -> list[tuple[int, Step]]:
    return [(i, s) for i, s in enumerate(steps_of(session)) if s.type != "intro"]


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
    """Build a session and answer every quiz step correctly on the first try."""
    session = await learning.build_session(db, child, topic_slug, now)
    if session is None:
        return None
    for index, _ in quiz_steps(session):
        await answer_correctly(db, child, session, index, now)
    await learning.finish_session(db, child, session.id, now)
    await db.commit()
    return session
