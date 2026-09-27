"""Lessons: how topics are cut, how they are numbered, and what may be played today."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, Word, WordProgress
from app.services import lessons

DAY1 = date(2026, 9, 22)
DAY2 = DAY1 + timedelta(days=1)


def test_parts_are_equal_and_at_most_ten() -> None:
    assert lessons.part_sizes(8) == [8]
    assert lessons.part_sizes(10) == [10]
    assert lessons.part_sizes(11) == [6, 5]
    assert lessons.part_sizes(12) == [6, 6]
    assert lessons.part_sizes(19) == [10, 9]
    assert lessons.part_sizes(25) == [9, 8, 8]
    assert lessons.part_sizes(0) == [0]


def test_lessons_follow_topic_order_and_word_order() -> None:
    topics = [
        Topic(id=2, slug="b", title_ru="Б", title_ka="", icon="", order=2),
        Topic(id=1, slug="a", title_ru="А", title_ka="", icon="", order=1),
    ]
    words = [
        Word(id=i, topic_id=t, slug=f"w{i}", ka="", tr="", ru="", image_value="", order=o)
        for i, (t, o) in enumerate(
            [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1)] + [(2, k) for k in range(2, 11)]
        )
    ]
    path = lessons.build_lessons(topics, words)
    assert [(lsn.number, lsn.topic.slug, lsn.part, lsn.parts) for lsn in path] == [
        (1, "a", 1, 1),
        (2, "b", 1, 2),
        (3, "b", 2, 2),
    ]
    assert [w.slug for w in path[0].words] == ["w0", "w1", "w2"]
    assert len(path[1].words) == 6 and len(path[2].words) == 5


async def test_real_content_makes_thirty_lessons(db: AsyncSession, seeded: None) -> None:
    path = await lessons.load_lessons(db)
    assert len(path) == 30
    assert [lsn.topic.slug for lsn in path[:5]] == [
        "letters-1",
        "letters-2",
        "letters-3",
        "letters-4",
        "syllables",
    ]
    assert all(1 <= len(lsn.words) <= lessons.MAX_WORDS_PER_LESSON for lsn in path)
    assert sum(len(lsn.words) for lsn in path) == 225


def state(pos: lessons.Position, number: int) -> lessons.LessonState:
    found = pos.get(number)
    assert found is not None
    return found


def topic_state(pos: lessons.Position, slug: str) -> lessons.TopicState:
    return next(t for t in pos.topics if t.topic.slug == slug)


def introduced(path: list[lessons.Lesson], *slugs: str) -> dict[int, WordProgress]:
    """Progress where every word of the named topics has been introduced."""
    return {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY1)
        for lsn in path
        if lsn.topic.slug in slugs
        for w in lsn.words
    }


def test_sections_come_from_the_slug() -> None:
    def topic(slug: str) -> Topic:
        return Topic(id=1, slug=slug, title_ru="", title_ka="", icon="", order=1)

    assert lessons.section_of(topic("letters-3")) == "letters"
    assert lessons.section_of(topic("syllables")) == "syllables"
    assert lessons.section_of(topic("colors")) == "words"


async def test_fresh_day_opens_every_topic_and_orders_lessons_within_it(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    pos = lessons.position(path, {}, [])
    assert [t.topic.slug for t in pos.topics] == [lsn.topic.slug for lsn in path if lsn.part == 1]
    assert all(t.status == "open" and not t.done for t in pos.topics)
    assert [t.section for t in pos.topics[:6]] == ["letters"] * 4 + ["syllables", "words"]

    # Any topic's first lesson can start; later parts of a topic wait for the first one.
    food = [s for s in pos.lessons if s.lesson.topic.slug == "food"]
    assert [(s.status, s.playable) for s in food] == [("current", True), ("locked", False)]
    assert state(pos, 1).playable and state(pos, 2).playable  # letters-1 and letters-2 alike
    assert pos.lesson_of_topic(food[0].lesson.topic.id) is food[0]


async def test_one_topic_per_section_per_day(db: AsyncSession, seeded: None) -> None:
    path = await lessons.load_lessons(db)
    colors = next(lsn for lsn in path if lsn.topic.slug == "colors")
    letters_2 = next(lsn for lsn in path if lsn.topic.slug == "letters-2")

    # A colors session today locks the other word topics; letters and syllables stay open.
    pos = lessons.position(path, {}, [colors.topic.id])
    assert topic_state(pos, "colors").status == "today"
    assert topic_state(pos, "greetings").status == "locked"
    assert topic_state(pos, "letters-2").status == "open"
    assert topic_state(pos, "syllables").status == "open"
    assert state(pos, colors.number).playable is True
    greetings = next(lsn for lsn in path if lsn.topic.slug == "greetings")
    assert (state(pos, greetings.number).status, state(pos, greetings.number).playable) == (
        "current",
        False,
    )

    # Letters chosen as well: two topics of the day, one per section.
    pos = lessons.position(path, {}, [colors.topic.id, letters_2.topic.id])
    assert topic_state(pos, "letters-2").status == "today"
    assert topic_state(pos, "letters-1").status == "locked"
    assert topic_state(pos, "colors").status == "today"

    # Every colors word shown: the lesson is done yet replayable while colors is today's topic.
    pos = lessons.position(path, introduced(path, "colors"), [colors.topic.id])
    assert (state(pos, colors.number).status, state(pos, colors.number).playable) == ("done", True)
    assert topic_state(pos, "colors").done is True

    # Another day, nothing chosen: colors can be replayed, and so can anything else.
    pos = lessons.position(path, introduced(path, "colors"), [])
    assert (state(pos, colors.number).status, state(pos, colors.number).playable) == ("done", True)
    assert state(pos, greetings.number).playable is True
    assert pos.lesson_of_topic(colors.topic.id) is state(pos, colors.number)

    # A replay of colors that day is the choice for words: greetings is locked again.
    pos = lessons.position(path, introduced(path, "colors"), [colors.topic.id])
    assert state(pos, greetings.number).playable is False


async def test_two_part_topic_opens_its_second_lesson_after_the_first(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    food = [lsn for lsn in path if lsn.topic.slug == "food"]
    first_done = {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY2) for w in food[0].words
    }
    pos = lessons.position(path, first_done, [food[0].topic.id])
    first, second = state(pos, food[0].number), state(pos, food[1].number)
    assert (first.status, first.playable) == ("done", True)
    assert (second.status, second.playable) == ("current", True)
    assert pos.lesson_of_topic(food[0].topic.id) is state(pos, food[1].number)
    assert topic_state(pos, "food").done is False


async def test_all_lessons_done(db: AsyncSession, seeded: None) -> None:
    path = await lessons.load_lessons(db)
    progress = introduced(path, *{lsn.topic.slug for lsn in path})
    pos = lessons.position(path, progress, [])
    assert pos.all_done
    assert all(t.done for t in pos.topics)
    assert all(s.status == "done" and s.playable for s in pos.lessons)  # every topic is a replay
