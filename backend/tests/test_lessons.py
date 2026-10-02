"""Lessons: how topics are cut, how they are numbered, and what may be played today."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Topic, TopicAccess, Word, WordProgress
from app.seed import load_topics
from app.services import lessons
from tests.conftest import CONTENT_DIR

DAY1 = date(2026, 9, 22)
DAY2 = DAY1 + timedelta(days=1)
DAY3 = DAY1 + timedelta(days=2)


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


async def test_real_content_makes_one_lesson_per_part(db: AsyncSession, seeded: None) -> None:
    topics = load_topics(CONTENT_DIR)
    path = await lessons.load_lessons(db)
    assert len(path) == sum(len(lessons.part_sizes(len(t.words))) for t in topics)
    assert [lsn.topic.slug for lsn in path[:5]] == [
        "letters-1",
        "letters-2",
        "letters-3",
        "letters-4",
        "syllables",
    ]
    assert all(1 <= len(lsn.words) <= lessons.MAX_WORDS_PER_LESSON for lsn in path)
    assert sum(len(lsn.words) for lsn in path) == sum(len(t.words) for t in topics)


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


def test_topic_inserted_behind_a_child_keeps_progress_and_opens_as_a_new_one() -> None:
    def topic(id_: int, slug: str, order: int) -> Topic:
        return Topic(id=id_, slug=slug, title_ru="", title_ka="", icon="", order=order)

    def words(topic_id: int) -> list[Word]:
        return [
            Word(
                id=topic_id * 10 + o,
                topic_id=topic_id,
                slug=f"w{o}",
                ka="",
                tr="",
                ru="",
                image_value="",
                order=o,
            )
            for o in range(3)
        ]

    old = [topic(1, "a", 10), topic(2, "b", 20), topic(3, "c", 30)]
    before = lessons.build_lessons(old, [w for t in old for w in words(t.id)])
    progress = introduced(before, "a", "b")
    first_days = {1: DAY1, 2: DAY2}

    # "new" goes in after "a", behind the child who has already finished "b".
    new = topic(4, "new", 15)
    after = lessons.build_lessons([*old, new], [w for t in [*old, new] for w in words(t.id)])
    assert [(lsn.number, lsn.topic.slug) for lsn in after] == [
        (1, "a"),
        (2, "new"),
        (3, "b"),
        (4, "c"),
    ]

    pos = lessons.position(after, progress, [], first_days, DAY3)
    assert [(t.topic.slug, t.done, t.status) for t in pos.topics] == [
        ("a", True, "open"),
        ("new", False, "open"),
        ("b", True, "open"),
        ("c", False, "open"),  # waits for "b", the topic right before it, not for "new"
    ]
    assert not pos.all_done

    # Once "new" is started, the one-new-topic-a-day rule holds "c" until tomorrow.
    pos = lessons.position(after, progress, [4], {**first_days, 4: DAY3}, DAY3)
    assert topic_state(pos, "new").status == "today"
    assert topic_state(pos, "c").status == "locked"


def test_sections_come_from_the_slug() -> None:
    def topic(slug: str) -> Topic:
        return Topic(id=1, slug=slug, title_ru="", title_ka="", icon="", order=1)

    assert lessons.section_of(topic("letters-3")) == "letters"
    assert lessons.section_of(topic("syllables")) == "syllables"
    assert lessons.section_of(topic("colors")) == "words"


async def test_fresh_day_opens_the_first_topic_of_each_section_and_orders_lessons_within_it(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    pos = lessons.position(path, {}, [], {}, DAY1)
    assert [t.topic.slug for t in pos.topics] == [lsn.topic.slug for lsn in path if lsn.part == 1]
    assert [t.section for t in pos.topics[:6]] == ["letters"] * 4 + ["syllables", "words"]
    assert not any(t.done for t in pos.topics)
    firsts = {"letters-1", "syllables", "basics"}
    assert all(t.status == ("open" if t.topic.slug in firsts else "locked") for t in pos.topics)

    # Only the first topic's lesson can start; in a later topic nothing can.
    basics = [s for s in pos.lessons if s.lesson.topic.slug == "basics"]
    assert [(s.status, s.playable) for s in basics] == [("current", True)]
    food = [s for s in pos.lessons if s.lesson.topic.slug == "food"]
    assert [(s.status, s.playable) for s in food] == [("current", False), ("locked", False)]
    assert state(pos, 1).playable and not state(pos, 2).playable  # letters-2 waits for letters-1
    assert pos.lesson_of_topic(food[0].lesson.topic.id) is food[0]


async def test_next_topic_waits_for_the_one_before_and_for_tomorrow(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}
    basics = [lsn for lsn in path if lsn.topic.slug == "basics"]
    colors = next(lsn for lsn in path if lsn.topic.slug == "colors")

    # Half of basics shown on day 1: colors waits for the rest, whatever the day.
    half = {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY1)
        for w in basics[0].words[:4]
    }
    pos = lessons.position(path, half, [], {ids["basics"]: DAY1}, DAY2)
    assert topic_state(pos, "basics").status == "open"
    assert topic_state(pos, "colors").status == "locked"
    assert state(pos, colors.number).playable is False

    # All of basics done on the day it was started: colors waits for tomorrow.
    done = introduced(path, "basics")
    pos = lessons.position(path, done, [ids["basics"]], {ids["basics"]: DAY1}, DAY1)
    assert topic_state(pos, "basics").status == "today"
    assert topic_state(pos, "colors").status == "locked"
    assert topic_state(pos, "letters-1").status == "open"  # another section: its own limit
    assert state(pos, colors.number).playable is False

    # Next day colors opens; the topic after it still waits for colors.
    pos = lessons.position(path, done, [], {ids["basics"]: DAY1}, DAY2)
    assert topic_state(pos, "colors").status == "open"
    assert topic_state(pos, "school-items").status == "locked"
    assert state(pos, colors.number).playable is True

    # Colors started that day: basics, done, stays open for a replay.
    first_days = {ids["basics"]: DAY1, ids["colors"]: DAY2}
    pos = lessons.position(path, done, [ids["colors"]], first_days, DAY2)
    assert topic_state(pos, "colors").status == "today"
    assert topic_state(pos, "basics").status == "open"
    assert all(state(pos, lsn.number).playable for lsn in basics)
    assert topic_state(pos, "school-items").status == "locked"

    # Two sections may each start a new topic the same day.
    first_days = {ids["basics"]: DAY1, ids["letters-1"]: DAY1}
    pos = lessons.position(path, {}, [ids["basics"], ids["letters-1"]], first_days, DAY1)
    assert topic_state(pos, "basics").status == "today"
    assert topic_state(pos, "letters-1").status == "today"
    assert topic_state(pos, "syllables").status == "open"


async def test_replay_and_restart_of_an_old_topic_leave_the_day_to_a_new_one(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}
    basics = next(lsn for lsn in path if lsn.topic.slug == "basics")
    school_items = next(lsn for lsn in path if lsn.topic.slug == "school-items")
    first_days = {ids["basics"]: DAY1, ids["colors"]: DAY2}
    both_done = introduced(path, "basics", "colors")

    # A replay of basics on day 3: basics is today's, school-items opens all the same.
    pos = lessons.position(path, both_done, [ids["basics"]], first_days, DAY3)
    assert topic_state(pos, "basics").status == "today"
    assert state(pos, basics.number).playable is True
    assert topic_state(pos, "school-items").status == "open"
    assert state(pos, school_items.number).playable is True

    # Basics started over the same day (its words forgotten): school-items still opens.
    colors_done = introduced(path, "colors")
    pos = lessons.position(path, colors_done, [ids["basics"]], first_days, DAY3)
    assert (topic_state(pos, "basics").status, topic_state(pos, "basics").done) == ("today", False)
    assert (state(pos, basics.number).status, state(pos, basics.number).playable) == (
        "current",
        True,
    )
    assert state(pos, school_items.number).playable is True

    # A started topic is never locked, even the day another one is new.
    first_days = {ids["basics"]: DAY1, ids["colors"]: DAY3}
    pos = lessons.position(path, colors_done, [ids["colors"]], first_days, DAY3)
    assert topic_state(pos, "basics").status == "open"
    assert state(pos, basics.number).playable is True


async def test_two_part_topic_opens_its_second_lesson_after_the_first(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    parts = [lsn for lsn in path if lsn.topic.slug == "syllables"]
    first_done = {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY2)
        for w in parts[0].words
    }
    topic_id = parts[0].topic.id
    pos = lessons.position(path, first_done, [topic_id], {topic_id: DAY2}, DAY2)
    first, second = state(pos, parts[0].number), state(pos, parts[1].number)
    assert (first.status, first.playable) == ("done", True)
    assert (second.status, second.playable) == ("current", True)  # the same day as the first
    assert pos.lesson_of_topic(topic_id) is state(pos, parts[1].number)
    assert topic_state(pos, "syllables").done is False


async def test_all_lessons_done(db: AsyncSession, seeded: None) -> None:
    path = await lessons.load_lessons(db)
    progress = introduced(path, *{lsn.topic.slug for lsn in path})
    pos = lessons.position(path, progress, [], {}, DAY1)
    assert pos.all_done
    assert all(t.done for t in pos.topics)
    assert all(s.status == "done" and s.playable for s in pos.lessons)  # every topic is a replay


async def test_parent_opens_a_topic_past_the_order_and_the_day(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}
    food = next(lsn for lsn in path if lsn.topic.slug == "food")

    # Nothing played yet: food is far down the section, the parent opens it all the same.
    pos = lessons.position(path, {}, [], {}, DAY1, {ids["food"]: "open"})
    assert (topic_state(pos, "food").status, topic_state(pos, "food").closed) == ("open", False)
    assert state(pos, food.number).playable is True
    assert topic_state(pos, "colors").status == "locked"  # the others keep the order

    # Basics started today: colors waits for tomorrow, the opened topic does not.
    first_days = {ids["basics"]: DAY1}
    pos = lessons.position(path, {}, [ids["basics"]], first_days, DAY1, {ids["food"]: "open"})
    assert topic_state(pos, "food").status == "open"

    # Once the child starts it, it is the section's new topic of the day like any other.
    done = introduced(path, "basics")
    first_days = {ids["basics"]: DAY1, ids["food"]: DAY2}
    pos = lessons.position(path, done, [ids["food"]], first_days, DAY2, {ids["food"]: "open"})
    assert topic_state(pos, "food").status == "today"
    assert topic_state(pos, "colors").status == "locked"


async def test_parent_closes_a_topic_whatever_its_progress(db: AsyncSession, seeded: None) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}
    basics = next(lsn for lsn in path if lsn.topic.slug == "basics")
    closed: dict[int, lessons.AccessMode] = {ids["basics"]: "closed"}

    # Done and replayed today: still locked, the replay included.
    done = introduced(path, "basics")
    pos = lessons.position(path, done, [ids["basics"]], {ids["basics"]: DAY1}, DAY2, closed)
    topic = topic_state(pos, "basics")
    assert (topic.status, topic.closed, topic.done) == ("locked", True, True)
    assert state(pos, basics.number).playable is False

    # Started and not finished: locked as well.
    half = {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY1)
        for w in basics.words[:4]
    }
    pos = lessons.position(path, half, [], {ids["basics"]: DAY1}, DAY2, closed)
    assert topic_state(pos, "basics").status == "locked"
    assert state(pos, basics.number).playable is False


async def test_closed_topic_does_not_hold_up_the_one_after_it(
    db: AsyncSession, seeded: None
) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}

    # Basics closed before it was ever played: colors takes its place at the head of the section.
    pos = lessons.position(path, {}, [], {}, DAY1, {ids["basics"]: "closed"})
    assert topic_state(pos, "basics").status == "locked"
    assert topic_state(pos, "colors").status == "open"
    assert topic_state(pos, "school-items").status == "locked"

    # Colors closed in the middle: school-items waits for basics, the topic before the closed one.
    closed: dict[int, lessons.AccessMode] = {ids["colors"]: "closed"}
    pos = lessons.position(path, {}, [], {}, DAY1, closed)
    assert topic_state(pos, "school-items").status == "locked"
    done = introduced(path, "basics")
    pos = lessons.position(path, done, [], {ids["basics"]: DAY1}, DAY2, closed)
    assert topic_state(pos, "school-items").status == "open"
    assert not any(t.closed for t in pos.topics if t.topic.slug != "colors")


async def test_topic_access_is_loaded_per_child(
    db: AsyncSession, seeded: None, child: Child
) -> None:
    path = await lessons.load_lessons(db)
    ids = {lsn.topic.slug: lsn.topic.id for lsn in path}
    assert await lessons.load_topic_access(db, child.id) == {}
    db.add_all(
        [
            TopicAccess(child_id=child.id, topic_id=ids["food"], mode="open"),
            TopicAccess(child_id=child.id, topic_id=ids["colors"], mode="closed"),
        ]
    )
    await db.flush()
    assert await lessons.load_topic_access(db, child.id) == {
        ids["food"]: "open",
        ids["colors"]: "closed",
    }
    assert await lessons.load_topic_access(db, child.id + 1) == {}
