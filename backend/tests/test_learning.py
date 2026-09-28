import random
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, ImageKind, Session, Topic, Word, WordProgress
from app.schemas.lesson import AnswerIn
from app.services import coins, learning, lessons
from app.services.errors import InvalidStep, LessonLocked, NotFound
from tests.helpers import (
    answer_correctly,
    at,
    build_for_topic,
    play_day,
    quiz_steps,
    skip_to,
    steps_of,
)

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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(1))
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

    session = await build_for_topic(db, child, "colors", at(DAY2), random.Random(2))
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
    session = await build_for_topic(db, child, "colors", at(DAY1, 18), random.Random(3))
    assert session is not None
    assert {s.word.slug for s in steps_of(session)} == {"yellow", "white", "black"}


async def test_review_only_session_is_none_when_nothing_waits(
    db: AsyncSession, child: Child
) -> None:
    assert await learning.build_session(db, child, None, at(DAY1)) is None
    await play_day(db, child, "colors", at(DAY1))  # answered today: nothing to review yet
    assert await learning.build_session(db, child, None, at(DAY1, 18)) is None
    review = await learning.build_session(db, child, None, at(DAY2), random.Random(20))
    assert review is not None and review.topic_id is None
    assert {s.word.slug for s in steps_of(review)} == {"red", "blue", "green"}
    assert all(s.type != "intro" for s in steps_of(review))


async def test_replay_of_todays_lesson_quizzes_every_word_and_pays_no_coin_twice(
    db: AsyncSession, child: Child
) -> None:
    number = await skip_to(db, child, "colors")
    for _ in range(4):  # 3 + 3 + 3 + 1 new words: the whole lesson in one day
        session = await learning.build_session(db, child, number, at(DAY1), random.Random(21))
        assert session is not None
        for index, _ in quiz_steps(session):
            await answer_correctly(db, child, session, index, at(DAY1))
    week = await coins.get_or_create_week(db, child.id, DAY1)
    assert week.coins == 10  # one coin per word, however many times it was quizzed

    replay = await learning.build_session(db, child, number, at(DAY1, 19), random.Random(22))
    assert replay is not None
    steps = steps_of(replay)
    assert not any(s.type == "intro" for s in steps)
    assert len(steps) == 10 and {s.word.topic_slug for s in steps} == {"colors"}
    for index, _ in quiz_steps(replay):
        assert (await answer_correctly(db, child, replay, index, at(DAY1, 19))).coins_gained == 0
    assert (await coins.get_or_create_week(db, child.id, DAY1)).coins == 10


async def test_one_topic_per_section_per_day_and_unknown_lesson_raises(
    db: AsyncSession, child: Child
) -> None:
    path = await lessons.load_lessons(db)
    food = [lsn.number for lsn in path if lsn.topic.slug == "food"]
    with pytest.raises(LessonLocked):  # the second part of a topic before the first
        await learning.build_session(db, child, food[1], at(DAY1))
    with pytest.raises(NotFound):
        await learning.build_session(db, child, 999, at(DAY1))

    colors = await skip_to(db, child, "colors")
    next_topic = path[colors].topic.slug  # the word topic that follows colors
    for _ in range(4):
        await play_day(db, child, "colors", at(DAY1))
    with pytest.raises(LessonLocked):  # another word topic: not today
        await learning.build_session(db, child, colors + 1, at(DAY1, 20))
    letters = await learning.build_session(db, child, 1, at(DAY1, 20), random.Random(23))
    assert letters is not None  # letters are a section of their own: still open today
    with pytest.raises(LessonLocked):  # and now letters-2 waits for tomorrow
        await learning.build_session(db, child, 2, at(DAY1, 21))

    tomorrow = await learning.build_session(db, child, colors + 1, at(DAY2), random.Random(23))
    assert tomorrow is not None
    assert [s.word.topic_slug for s in steps_of(tomorrow) if s.type == "intro"] == [next_topic] * 3
    with pytest.raises(LessonLocked):  # yesterday's topic is locked once another one is chosen
        await learning.build_session(db, child, colors, at(DAY2, 13))


async def test_replay_of_an_old_topic_is_the_choice_of_the_day(
    db: AsyncSession, child: Child
) -> None:
    colors = await skip_to(db, child, "colors")
    for _ in range(4):
        await play_day(db, child, "colors", at(DAY1))
    replay = await learning.build_session(db, child, colors, at(DAY2), random.Random(24))
    assert replay is not None and not any(s.type == "intro" for s in steps_of(replay))
    with pytest.raises(LessonLocked):  # colors took the word section for today
        await learning.build_session(db, child, colors + 1, at(DAY2, 13))


async def test_restart_of_a_topic_shows_its_words_again_and_keeps_stages_and_coins(
    db: AsyncSession, child: Child
) -> None:
    colors = await skip_to(db, child, "colors")
    for _ in range(4):
        await play_day(db, child, "colors", at(DAY1))
    assert (await coins.get_or_create_week(db, child.id, DAY1)).coins == 10
    stage_before = (await progress_of(db, child, "red")).stage
    assert stage_before > 0

    with pytest.raises(NotFound):
        await learning.restart_topic(db, child, "no-such-topic", at(DAY2))

    session = await learning.restart_topic(db, child, "colors", at(DAY2), random.Random(25))
    assert session is not None
    intros = [s.word.slug for s in steps_of(session) if s.type == "intro"]
    assert intros == ["red", "blue", "green"]  # the first lesson, from its first word
    assert (await progress_of(db, child, "red")).stage == stage_before  # nothing forgotten
    assert (await progress_of(db, child, "yellow")).introduced is False

    path = await lessons.load_lessons(db)
    position = lessons.position(path, await lessons.load_progress(db, child.id), [])
    state = position.get(colors)
    assert state is not None and (state.status, state.introduced) == ("current", 3)
    assert (await coins.get_or_create_week(db, child.id, DAY1)).coins == 10  # week 1 untouched

    with pytest.raises(LessonLocked):  # colors took the word section for today
        await learning.restart_topic(db, child, "food", at(DAY2, 13))


async def test_text_cards_are_reviewed_with_listen_only_and_carry_anchor(
    db: AsyncSession, child: Child
) -> None:
    anchor = {"ka": "ბურთი", "tr": "бурти", "ru": "мяч", "emoji": "⚽"}
    topic = Topic(
        slug=f"letters-{uuid.uuid4().hex[:6]}",
        title_ru="Буквы",
        title_ka="ასოები",
        icon="🔤",
        order=999,  # after every content topic, whose orders go in tens
    )
    db.add(topic)
    await db.flush()
    for i, letter in enumerate("ბდლმსა"):
        db.add(
            Word(
                topic_id=topic.id,
                slug=f"l{i}",
                ka=letter,
                tr="?",
                ru=f"буква {letter}",
                image_kind=ImageKind.text,
                image_value=letter,
                anchor=anchor,
                order=i,
            )
        )
    await db.flush()

    # Nothing here is committed: the shared database must not gain a topic other tests count.
    first = await build_for_topic(db, child, topic.slug, at(DAY1))
    assert first is not None
    intro = steps_of(first)[0]
    assert intro.word.image.kind is ImageKind.text
    assert intro.word.anchor is not None and intro.word.anchor.emoji == "⚽"
    for index, _ in quiz_steps(first):
        await answer_correctly(db, child, first, index, at(DAY1))

    # Day 2: the letters come back for review; whatever the dice say, never `recall`.
    for seed in range(10):
        session = await build_for_topic(db, child, topic.slug, at(DAY2), random.Random(seed))
        assert session is not None
        review = [s for s in steps_of(session) if s.type != "intro"]
        assert review and all(s.type == "listen" for s in review)
        assert all(len(s.options) == 4 for s in review)


# --- answers, stages and coins -----------------------------------------------


async def test_first_try_correct_earns_one_coin_and_a_stage(db: AsyncSession, child: Child) -> None:
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(4))
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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(5))
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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(6))
    assert session is not None
    # Hand-craft a second quiz step for the same word inside the same session.
    first_index, step = quiz_steps(session)[0]
    session.steps = [*session.steps, session.steps[first_index]]
    await db.flush()
    dup_index = len(session.steps) - 1

    await answer_correctly(db, child, session, first_index, at(DAY1, 9))
    again = await answer_correctly(db, child, session, dup_index, at(DAY1, 21))
    assert again.coins_gained == 0  # the word was already answered today: no second coin
    progress = await progress_of(db, child, step.word.slug)
    assert progress.stage == 1  # and the stage moved only once today


async def test_word_is_learned_on_third_day_with_bonus(db: AsyncSession, child: Child) -> None:
    await play_day(db, child, "colors", at(DAY1))
    await play_day(db, child, "colors", at(DAY2))
    session = await build_for_topic(db, child, "colors", at(DAY3), random.Random(7))
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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(8))
    assert session is not None
    gains = [
        (await answer_correctly(db, child, session, i, at(DAY1))).coins_gained
        for i, _ in quiz_steps(session)
    ]
    assert gains == [1, 1, 0]
    week = await coins.get_or_create_week(db, child.id, DAY1)
    assert week.coins == 2


async def test_repeated_client_answer_id_is_idempotent(db: AsyncSession, child: Child) -> None:
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(9))
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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(10))
    assert session is not None
    index, _ = quiz_steps(session)[0]
    await answer_correctly(db, child, session, index, at(DAY1))
    replay = await answer_correctly(db, child, session, index, at(DAY1))
    assert (replay.correct, replay.coins_gained, replay.week_coins) == (True, 0, 1)


async def test_invalid_answers_are_rejected(db: AsyncSession, child: Child) -> None:
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(11))
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
    session = await build_for_topic(db, child, "colors", at(sunday, 23, 30), random.Random(12))
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
    session = await build_for_topic(db, child, "colors", at(DAY1), random.Random(13))
    assert session is not None
    first = await learning.finish_session(db, child, session.id, at(DAY1, 12, 5))
    second = await learning.finish_session(db, child, session.id, at(DAY1, 12, 9))
    stored = (await db.execute(select(Session).where(Session.id == session.id))).scalar_one()
    assert stored.finished_at == at(DAY1, 12, 5)
    assert stored.study_date == DAY1
    assert first == second
