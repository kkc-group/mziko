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
from app.services import lessons
from app.services.errors import InvalidStep, LessonLocked, NotFound, SessionFinished

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
    lesson_number: int | None,
    now: datetime,
    rng: random.Random | None = None,
) -> Session | None:
    """Create a session for lesson `lesson_number`, or a review-only one for None.

    The lesson must be playable today (see services.lessons), else LessonLocked.
    The session itself makes its topic the section's topic of the day.
    Up to 3 of its words not yet shown are introduced (in order). The quiz then
    reviews: first the lesson's own words not answered correctly today, then the
    longest-waiting unlearned words of earlier lessons, 4 in all. Replaying a
    finished lesson quizzes every word of it plus up to 4 older ones.
    Returns None when there is nothing at all to do.
    """
    rng = rng or random.Random()
    today = local_date(now)
    topics = await _topics_by_id(db)
    progress_by_word = await lessons.load_progress(db, child.id)
    today_topics = await lessons.load_today_topics(db, child.id, today)
    position = lessons.position(await lessons.load_lessons(db), progress_by_word, today_topics)

    lesson: lessons.Lesson | None = None
    if lesson_number is not None:
        state = position.get(lesson_number)
        if state is None:
            raise NotFound(f"lesson {lesson_number}")
        if not state.playable:
            raise LessonLocked(f"lesson {lesson_number} cannot be played today")
        lesson = state.lesson

    def introduced(word: Word) -> bool:
        p = progress_by_word.get(word.id)
        return p is not None and p.introduced

    def answered_today(word: Word) -> bool:
        p = progress_by_word.get(word.id)
        return p is not None and p.last_correct_date == today

    lesson_words: list[Word] = list(lesson.words) if lesson else []
    new_words = [w for w in lesson_words if not introduced(w)][:NEW_WORDS_PER_SESSION]
    if new_words:
        own_reviews = [w for w in lesson_words if introduced(w) and not answered_today(w)]
        own_reviews = own_reviews[:REVIEW_WORDS_PER_SESSION]
        older_limit = REVIEW_WORDS_PER_SESSION - len(own_reviews)
    else:  # a replay: the whole lesson, plus the usual share of older words
        own_reviews = lesson_words
        older_limit = REVIEW_WORDS_PER_SESSION

    older_stmt = (
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
            Word.id.not_in([w.id for w in lesson_words]),
        )
        .order_by(WordProgress.last_correct_date.asc().nulls_first(), Word.id)
        .limit(older_limit)
    )
    older_reviews = list((await db.execute(older_stmt)).scalars()) if older_limit else []
    review_words = own_reviews + older_reviews

    if not new_words and not review_words:
        return None

    introduced_ids = {w.id for w in lesson_words if introduced(w)}
    for word in new_words:
        progress = await _get_or_create_progress(db, child.id, word.id)
        progress.introduced = True
        progress.introduced_on = today
        introduced_ids.add(word.id)

    # Distractors come from the same topic as the correct word.
    pools: dict[int, list[Word]] = {}
    for word in [*new_words, *review_words]:
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
        topic_id=lesson.topic.id if lesson else None,
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

    Coins are granted only for a first-attempt correct answer, once per step and
    only the first time the word is answered correctly that day: replaying a
    lesson earns nothing twice. A repeated `client_answer_id` returns the stored
    verdict without crediting again.
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
        progress = await _get_or_create_progress(db, child.id, word.id)
        first_today = progress.last_correct_date is None or progress.last_correct_date < today
        if not already_credited and first_today:
            gained = await coin_service.add_coins(
                db, child, week, COINS_PER_ANSWER, CoinReason.answer, answer.id
            )
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
