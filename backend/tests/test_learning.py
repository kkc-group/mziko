import random
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Session, Topic, Word, WordProgress
from app.schemas.lesson import AnswerIn
from app.services import coins, learning
from app.services.errors import InvalidStep, NotFound
from tests.helpers import answer_correctly, at, play_day, quiz_steps, steps_of

DAY1 = date(2026, 9, 22)  # Tuesday
DAY2 = DAY1 + timedelta(days=1)
DAY3 = DAY1 + timedelta(days=2)


async def progress_of(db: AsyncSession, child: Child, slug: str) -> WordProgress:
    stmt = (
        select(WordProgress).join(Word).where(WordProgress.child_id == child.id, Word.slug == slug)
    )
    return (await db.execute(stmt)).scalar_one()


# --- session building -------------------------------------------------------


async def test_first_session_introduces_three_topic_words_in_order(
    db: AsyncSession, child: Child
) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(1))
    assert session is not None
    steps = steps_of(session)

    intros = [s for s in steps if s.type == "intro"]
    assert [s.word.slug for s in intros] == ["red", "blue", "green"]
    assert steps[:3] == intros  # intros come first

    quiz = steps[3:]
    assert len(quiz) == 3 and all(s.type == "listen" for s in quiz)
    assert {s.word.slug for s in quiz} == {"red", "blue", "green"}
    for s in quiz:
        assert len(s.options) == 4
        assert s.word.slug in {o.slug for o in s.options}
        assert all(o.topic_slug == "colors" for o in s.options)  # distractors same topic
        assert s.word.audio_url == f"/media/audio/colors/{s.word.slug}.mp3"

    for slug in ("red", "blue", "green"):
        assert (await progress_of(db, child, slug)).introduced is True


async def test_review_words_come_from_all_topics_and_keep_their_own_distractors(
    db: AsyncSession, child: Child
) -> None:
    await play_day(db, child, "basics", at(DAY1))  # dog, cat, apple introduced & stage 1

    session = await learning.build_session(db, child, "colors", at(DAY2), random.Random(2))
    assert session is not None
    steps = steps_of(session)
    assert [s.word.slug for s in steps if s.type == "intro"] == ["red", "blue", "green"]

    review = [s for s in steps if s.type != "intro" and s.word.topic_slug == "basics"]
    assert {s.word.slug for s in review} == {"dog", "cat", "apple"}
    for s in review:
        assert s.type in ("listen", "recall")
        assert all(o.topic_slug == "basics" for o in s.options)
        assert len(s.options) == (4 if s.type == "listen" else 3)


async def test_review_skips_words_answered_today_and_learned_words(
    db: AsyncSession, child: Child
) -> None:
    await play_day(db, child, "colors", at(DAY1))
    # Same day again: the three words were answered today, so no review; next 3 new words.
    session = await learning.build_session(db, child, "colors", at(DAY1, 18), random.Random(3))
    assert session is not None
    assert {s.word.slug for s in steps_of(session)} == {"yellow", "white", "black"}


async def test_empty_plan_when_nothing_to_learn_or_review(db: AsyncSession, child: Child) -> None:
    topic = (await db.execute(select(Topic).where(Topic.slug == "colors"))).scalar_one()
    words = (await db.execute(select(Word).where(Word.topic_id == topic.id))).scalars()
    for w in words:
        db.add(
            WordProgress(
                child_id=child.id, word_id=w.id, stage=3, introduced=True, last_correct_date=DAY1
            )
        )
    await db.flush()
    assert await learning.build_session(db, child, "colors", at(DAY2)) is None


async def test_unknown_topic_raises(db: AsyncSession, child: Child) -> None:
    with pytest.raises(NotFound):
        await learning.build_session(db, child, "nope", at(DAY1))


# --- answers, stages and coins -----------------------------------------------


async def test_first_try_correct_earns_one_coin_and_a_stage(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(4))
    assert session is not None
    index, step = quiz_steps(session)[0]

    result = await answer_correctly(db, child, session, index, at(DAY1))
    assert (result.correct, result.coins_gained, result.word_learned) == (True, 1, False)
    assert result.week_coins == 1
    assert str(result.week_lari) == "0.1"

    progress = await progress_of(db, child, step.word.slug)
    assert (progress.stage, progress.last_correct_date) == (1, DAY1)


async def test_wrong_answer_gives_nothing_and_second_try_gives_no_coins(
    db: AsyncSession, child: Child
) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(5))
    assert session is not None
    index, step = quiz_steps(session)[0]
    wrong = next(o.slug for o in step.options if o.slug != step.word.slug)

    bad = await learning.submit_answer(
        db,
        child,
        session.id,
        AnswerIn(step_index=index, word_slug=wrong, attempt=1, client_answer_id=uuid.uuid4()),
        at(DAY1),
    )
    assert (bad.correct, bad.coins_gained, bad.week_coins) == (False, 0, 0)

    second = await answer_correctly(db, child, session, index, at(DAY1), attempt=2)
    assert (second.correct, second.coins_gained, second.week_coins) == (True, 0, 0)
    assert (await progress_of(db, child, step.word.slug)).stage == 0


async def test_stage_grows_at_most_once_per_day(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(6))
    assert session is not None
    # Hand-craft a second quiz step for the same word inside the same session.
    first_index, step = quiz_steps(session)[0]
    session.steps = [*session.steps, session.steps[first_index]]
    await db.flush()
    dup_index = len(session.steps) - 1

    await answer_correctly(db, child, session, first_index, at(DAY1, 9))
    again = await answer_correctly(db, child, session, dup_index, at(DAY1, 21))
    assert again.coins_gained == 1  # a different step still pays its coin
    progress = await progress_of(db, child, step.word.slug)
    assert progress.stage == 1  # but the stage moved only once today


async def test_word_is_learned_on_third_day_with_bonus(db: AsyncSession, child: Child) -> None:
    await play_day(db, child, "colors", at(DAY1))
    await play_day(db, child, "colors", at(DAY2))
    session = await learning.build_session(db, child, "colors", at(DAY3), random.Random(7))
    assert session is not None

    red_index = next(i for i, s in quiz_steps(session) if s.word.slug == "red")
    result = await answer_correctly(db, child, session, red_index, at(DAY3))
    assert (result.coins_gained, result.word_learned) == (6, True)

    progress = await progress_of(db, child, "red")
    assert progress.stage == 3
    assert progress.learned_at == at(DAY3)

    summary = await learning.finish_session(db, child, session.id, at(DAY3))
    assert "red" in {w.slug for w in summary.learned}
    assert summary.coins_gained >= 6


async def test_weekly_cap_clips_coins(db: AsyncSession, child: Child) -> None:
    child.rate, child.cap_lari = 1, 2  # only 2 coins per week
    await db.flush()
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(8))
    assert session is not None
    gains = [
        (await answer_correctly(db, child, session, i, at(DAY1))).coins_gained
        for i, _ in quiz_steps(session)
    ]
    assert gains == [1, 1, 0]
    week = await coins.get_or_create_week(db, child.id, DAY1)
    assert week.coins == 2


async def test_repeated_client_answer_id_is_idempotent(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(9))
    assert session is not None
    index, step = quiz_steps(session)[0]
    payload = AnswerIn(
        step_index=index, word_slug=step.word.slug, attempt=1, client_answer_id=uuid.uuid4()
    )
    first = await learning.submit_answer(db, child, session.id, payload, at(DAY1))
    second = await learning.submit_answer(db, child, session.id, payload, at(DAY1, 12, 1))
    assert first == second
    assert second.week_coins == 1


async def test_same_step_cannot_be_farmed_with_new_ids(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(10))
    assert session is not None
    index, _ = quiz_steps(session)[0]
    await answer_correctly(db, child, session, index, at(DAY1))
    replay = await answer_correctly(db, child, session, index, at(DAY1))
    assert (replay.correct, replay.coins_gained, replay.week_coins) == (True, 0, 1)


async def test_invalid_answers_are_rejected(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(11))
    assert session is not None
    with pytest.raises(InvalidStep):  # intro step
        await learning.submit_answer(
            db,
            child,
            session.id,
            AnswerIn(step_index=0, word_slug="red", attempt=1, client_answer_id=uuid.uuid4()),
            at(DAY1),
        )
    index, _ = quiz_steps(session)[0]
    with pytest.raises(InvalidStep):  # not among the options
        await learning.submit_answer(
            db,
            child,
            session.id,
            AnswerIn(step_index=index, word_slug="dog", attempt=1, client_answer_id=uuid.uuid4()),
            at(DAY1),
        )
    with pytest.raises(NotFound):  # somebody else's session
        await learning.submit_answer(
            db,
            child,
            uuid.uuid4(),
            AnswerIn(step_index=index, word_slug="red", attempt=1, client_answer_id=uuid.uuid4()),
            at(DAY1),
        )


# --- weeks ------------------------------------------------------------------


async def test_week_boundary_follows_tbilisi_midnight(db: AsyncSession, child: Child) -> None:
    sunday, monday = date(2026, 9, 27), date(2026, 9, 28)
    session = await learning.build_session(
        db, child, "colors", at(sunday, 23, 30), random.Random(12)
    )
    assert session is not None
    (i1, _), (i2, _), *_ = quiz_steps(session)

    late_sunday = await answer_correctly(db, child, session, i1, at(sunday, 23, 30))
    assert late_sunday.week_coins == 1

    # 00:30 Monday in Tbilisi is still 20:30 Sunday in UTC; the coin must land in the new week.
    early_monday = await answer_correctly(db, child, session, i2, at(monday, 0, 30))
    assert early_monday.week_coins == 1

    old_week = await coins.get_or_create_week(db, child.id, sunday)
    new_week = await coins.get_or_create_week(db, child.id, monday)
    assert (old_week.coins, new_week.coins) == (1, 1)


async def test_finish_marks_study_day_and_is_idempotent(db: AsyncSession, child: Child) -> None:
    session = await learning.build_session(db, child, "colors", at(DAY1), random.Random(13))
    assert session is not None
    first = await learning.finish_session(db, child, session.id, at(DAY1, 12, 5))
    second = await learning.finish_session(db, child, session.id, at(DAY1, 12, 9))
    stored = (await db.execute(select(Session).where(Session.id == session.id))).scalar_one()
    assert stored.finished_at == at(DAY1, 12, 5)
    assert stored.study_date == DAY1
    assert first == second
