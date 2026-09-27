"""Lesson logic: building a session plan, grading answers, finishing a session.

The server is the source of truth: it picks words, generates options and is the
only place coins are credited. `now` is always passed in (see app.core.clock).
"""

import random
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_date
from app.models import (
    Answer,
    Child,
    CoinReason,
    ImageKind,
    Session,
    Topic,
    Word,
    WordProgress,
)
from app.schemas.lesson import (
    AnchorOut,
    AnswerIn,
    AnswerResult,
    ImageOut,
    SessionSummary,
    Step,
    WordOut,
)
from app.services import coins as coin_service
from app.services.errors import InvalidStep, NotFound, SessionFinished

NEW_WORDS_PER_SESSION = 3
REVIEW_WORDS_PER_SESSION = 4
LISTEN_OPTIONS = 4
RECALL_OPTIONS = 3
LEARNED_STAGE = 3
COINS_PER_ANSWER = 1
COINS_PER_LEARNED_WORD = 5


def word_out(word: Word, topic_slug: str) -> WordOut:
    return WordOut(
        slug=word.slug,
        topic_slug=topic_slug,
        ka=word.ka,
        tr=word.tr,
        ru=word.ru,
        image=ImageOut(kind=word.image_kind, value=word.image_value),
        anchor=AnchorOut.model_validate(word.anchor) if word.anchor else None,
        audio_url=f"/media/audio/{topic_slug}/{word.slug}.mp3",
    )


async def _topics_by_id(db: AsyncSession) -> dict[int, Topic]:
    return {t.id: t for t in (await db.execute(select(Topic))).scalars()}


async def _topic_words(db: AsyncSession, topic_id: int) -> list[Word]:
    stmt = select(Word).where(Word.topic_id == topic_id).order_by(Word.order)
    return list((await db.execute(stmt)).scalars())


async def _get_or_create_progress(db: AsyncSession, child_id: int, word_id: int) -> WordProgress:
    stmt = select(WordProgress).where(
        WordProgress.child_id == child_id, WordProgress.word_id == word_id
    )
    progress = (await db.execute(stmt)).scalar_one_or_none()
    if progress is None:
        progress = WordProgress(child_id=child_id, word_id=word_id)
        db.add(progress)
        await db.flush()
    return progress


def _pick_distractors(
    pool: Sequence[Word], correct: Word, count: int, rng: random.Random
) -> list[Word]:
    candidates = [w for w in pool if w.id != correct.id]
    return rng.sample(candidates, min(count, len(candidates)))


async def build_session(
    db: AsyncSession,
    child: Child,
    topic_slug: str,
    now: datetime,
    rng: random.Random | None = None,
) -> Session | None:
    """Create today's lesson for `topic_slug`, or return None when there is nothing to do.

    New words (up to 3, in topic order) are marked introduced here. Review words
    (up to 4) come from every topic: introduced, not yet learned, and not answered
    correctly today; the longest-waiting first.
    """
    rng = rng or random.Random()
    today = local_date(now)
    topics = await _topics_by_id(db)
    topic = next((t for t in topics.values() if t.slug == topic_slug), None)
    if topic is None:
        raise NotFound(f"topic {topic_slug!r}")

    introduced_ids = set(
        (
            await db.execute(
                select(WordProgress.word_id).where(
                    WordProgress.child_id == child.id, WordProgress.introduced.is_(True)
                )
            )
        ).scalars()
    )
    topic_words = await _topic_words(db, topic.id)
    new_words = [w for w in topic_words if w.id not in introduced_ids][:NEW_WORDS_PER_SESSION]

    review_stmt = (
        select(Word)
        .join(WordProgress, WordProgress.word_id == Word.id)
        .where(
            WordProgress.child_id == child.id,
            WordProgress.introduced.is_(True),
            WordProgress.stage < LEARNED_STAGE,
            or_(
                WordProgress.last_correct_date.is_(None),
                WordProgress.last_correct_date < today,
            ),
        )
        .order_by(WordProgress.last_correct_date.asc().nulls_first(), Word.id)
        .limit(REVIEW_WORDS_PER_SESSION)
    )
    review_words = list((await db.execute(review_stmt)).scalars())

    if not new_words and not review_words:
        return None

    for word in new_words:
        progress = await _get_or_create_progress(db, child.id, word.id)
        progress.introduced = True

    # Distractors come from the same topic as the correct word.
    pools: dict[int, list[Word]] = {topic.id: topic_words}
    for word in review_words:
        if word.topic_id not in pools:
            pools[word.topic_id] = await _topic_words(db, word.topic_id)

    def out(word: Word) -> WordOut:
        return word_out(word, topics[word.topic_id].slug)

    def listen_step(word: Word) -> Step:
        options = [word, *_pick_distractors(pools[word.topic_id], word, LISTEN_OPTIONS - 1, rng)]
        rng.shuffle(options)
        return Step(type="listen", word=out(word), options=[out(o) for o in options])

    def recall_step(word: Word) -> Step:
        pool = pools[word.topic_id]
        known = [w for w in pool if w.id in introduced_ids or w.id == word.id]
        distractors = _pick_distractors(known, word, RECALL_OPTIONS - 1, rng)
        if len(distractors) < RECALL_OPTIONS - 1:
            rest = [w for w in pool if w not in distractors]
            distractors += _pick_distractors(rest, word, RECALL_OPTIONS - 1 - len(distractors), rng)
        options = [word, *distractors]
        rng.shuffle(options)
        return Step(type="recall", word=out(word), options=[out(o) for o in options])

    def review_step(word: Word) -> Step:
        # A text card *is* the word, so "picture -> pick the word" would give the answer away.
        if word.image_kind is ImageKind.text:
            return listen_step(word)
        return rng.choice((listen_step, recall_step))(word)

    steps: list[Step] = [Step(type="intro", word=out(w)) for w in new_words]
    quiz: list[Step] = [listen_step(w) for w in new_words]
    quiz += [review_step(w) for w in review_words]
    rng.shuffle(quiz)
    steps += quiz

    session = Session(
        child_id=child.id,
        topic_id=topic.id,
        study_date=today,
        steps=[s.model_dump(mode="json") for s in steps],
    )
    db.add(session)
    await db.flush()
    return session


async def _load_session(db: AsyncSession, child: Child, session_id: uuid.UUID) -> Session:
    stmt = select(Session).where(Session.id == session_id, Session.child_id == child.id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        raise NotFound(f"session {session_id}")
    return session


async def _week_state(
    db: AsyncSession, child: Child, now: datetime, *, for_update: bool = False
) -> tuple[int, int]:
    week = await coin_service.get_or_create_week(
        db, child.id, local_date(now), for_update=for_update
    )
    return week.id, week.coins


def _result(child: Child, answer: Answer, week_coins: int) -> AnswerResult:
    return AnswerResult(
        correct=answer.correct,
        coins_gained=answer.coins_gained,
        word_learned=answer.word_learned,
        week_coins=week_coins,
        week_lari=coin_service.lari_for(week_coins, child.rate, child.cap_lari),
    )


async def submit_answer(
    db: AsyncSession,
    child: Child,
    session_id: uuid.UUID,
    payload: AnswerIn,
    now: datetime,
) -> AnswerResult:
    """Grade one answer and credit coins.

    Coins are granted only for a first-attempt correct answer, once per step.
    A repeated `client_answer_id` returns the stored verdict without crediting again.
    """
    session = await _load_session(db, child, session_id)

    previous = (
        await db.execute(select(Answer).where(Answer.client_answer_id == payload.client_answer_id))
    ).scalar_one_or_none()
    if previous is not None:
        _, week_coins = await _week_state(db, child, now)
        return _result(child, previous, week_coins)

    if session.finished_at is not None:
        raise SessionFinished(str(session_id))
    if payload.step_index >= len(session.steps):
        raise InvalidStep(f"step {payload.step_index} out of range")
    step = Step.model_validate(session.steps[payload.step_index])
    if step.type == "intro":
        raise InvalidStep("intro steps take no answer")
    chosen = next((o for o in step.options if o.slug == payload.word_slug), None)
    if chosen is None:
        raise InvalidStep(f"{payload.word_slug!r} is not an option of step {payload.step_index}")

    word = (
        await db.execute(
            select(Word)
            .join(Topic)
            .where(Topic.slug == chosen.topic_slug, Word.slug == chosen.slug)
        )
    ).scalar_one()
    correct = chosen.slug == step.word.slug

    answer = Answer(
        session_id=session.id,
        client_answer_id=payload.client_answer_id,
        step_index=payload.step_index,
        word_id=word.id,
        attempt=payload.attempt,
        correct=correct,
        coins_gained=0,
        word_learned=False,
    )
    db.add(answer)
    await db.flush()

    today = local_date(now)
    week = await coin_service.get_or_create_week(db, child.id, today, for_update=True)

    if correct and payload.attempt == 1:
        already_credited = (
            await db.execute(
                select(
                    exists().where(
                        Answer.session_id == session.id,
                        Answer.step_index == payload.step_index,
                        Answer.correct.is_(True),
                        Answer.id != answer.id,
                    )
                )
            )
        ).scalar_one()
        if not already_credited:
            gained = await coin_service.add_coins(
                db, child, week, COINS_PER_ANSWER, CoinReason.answer, answer.id
            )
            progress = await _get_or_create_progress(db, child.id, word.id)
            if progress.last_correct_date is None or progress.last_correct_date < today:
                progress.stage = min(LEARNED_STAGE, progress.stage + 1)
                progress.last_correct_date = today
                if progress.stage == LEARNED_STAGE and progress.learned_at is None:
                    progress.learned_at = now
                    answer.word_learned = True
                    gained += await coin_service.add_coins(
                        db, child, week, COINS_PER_LEARNED_WORD, CoinReason.word_learned, answer.id
                    )
            answer.coins_gained = gained
            await db.flush()

    return _result(child, answer, week.coins)


async def finish_session(
    db: AsyncSession, child: Child, session_id: uuid.UUID, now: datetime
) -> SessionSummary:
    """Mark the session finished (which marks its study day) and summarise it. Idempotent."""
    session = await _load_session(db, child, session_id)
    if session.finished_at is None:
        session.finished_at = now
        await db.flush()

    answers = list(
        (await db.execute(select(Answer).where(Answer.session_id == session.id))).scalars()
    )
    learned_ids = [a.word_id for a in answers if a.word_learned]
    learned: list[WordOut] = []
    if learned_ids:
        topics = await _topics_by_id(db)
        words = (await db.execute(select(Word).where(Word.id.in_(learned_ids)))).scalars()
        learned = [word_out(w, topics[w.topic_id].slug) for w in words]

    _, week_coins = await _week_state(db, child, now)
    return SessionSummary(
        session_id=session.id,
        coins_gained=sum(a.coins_gained for a in answers),
        learned=learned,
        week_coins=week_coins,
        week_lari=coin_service.lari_for(week_coins, child.rate, child.cap_lari),
    )
