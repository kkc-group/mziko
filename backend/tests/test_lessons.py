"""Lessons: how topics are cut, how they are numbered, and what may be played today."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Topic, Word, WordProgress
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


async def test_position_one_new_topic_per_day(db: AsyncSession, child: Child) -> None:
    path = await lessons.load_lessons(db)
    colors = next(lsn for lsn in path if lsn.topic.slug == "colors")  # one lesson of 10
    greetings = next(lsn for lsn in path if lsn.topic.slug == "greetings")
    assert greetings.number == colors.number + 1

    def progress_after(introduced_on: dict[int, date]) -> dict[int, WordProgress]:
        out: dict[int, WordProgress] = {}
        for lsn in path:
            for w in lsn.words:
                if lsn.number < colors.number:
                    out[w.id] = WordProgress(word_id=w.id, introduced=True, introduced_on=DAY1)
                elif w.id in introduced_on:
                    out[w.id] = WordProgress(
                        word_id=w.id, introduced=True, introduced_on=introduced_on[w.id]
                    )
        return out

    # Fresh day: colors is current and playable; greetings is locked.
    pos = lessons.position(path, progress_after({}), DAY2)
    assert pos.current is not None and pos.current.lesson is colors
    assert state(pos, colors.number).playable is True
    assert state(pos, greetings.number).status == "locked"
    assert pos.today_topic_id is None

    # Three colors words shown today: colors stays playable, greetings stays locked.
    three = {w.id: DAY2 for w in colors.words[:3]}
    pos = lessons.position(path, progress_after(three), DAY2)
    assert pos.today_topic_id == colors.topic.id
    assert state(pos, colors.number).introduced == 3 and state(pos, colors.number).playable

    # Every colors word shown today: colors is done yet replayable; greetings is current but
    # not playable until tomorrow (one new topic per day).
    every = {w.id: DAY2 for w in colors.words}
    pos = lessons.position(path, progress_after(every), DAY2)
    colors_state, greetings_state = state(pos, colors.number), state(pos, greetings.number)
    assert (colors_state.status, colors_state.playable) == ("done", True)
    assert (greetings_state.status, greetings_state.playable) == ("current", False)
    assert pos.current is greetings_state

    # Tomorrow greetings opens and colors is no longer replayable.
    pos = lessons.position(path, progress_after(every), DAY2 + timedelta(days=1))
    assert state(pos, greetings.number).playable is True
    assert state(pos, colors.number).playable is False


async def test_all_lessons_done_means_no_current(db: AsyncSession, child: Child) -> None:
    path = await lessons.load_lessons(db)
    progress = {
        w.id: WordProgress(word_id=w.id, introduced=True, introduced_on=DAY1)
        for lsn in path
        for w in lsn.words
    }
    pos = lessons.position(path, progress, DAY2)
    assert pos.current is None
    assert all(s.status == "done" and not s.playable for s in pos.lessons)
