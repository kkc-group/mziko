"""Lessons: topics cut into equal parts of at most MAX_WORDS_PER_LESSON words, numbered in order.

Nothing about lessons is stored. They are derived from topic order and word
order, and a child's position from word progress:

- a lesson is done when every word in it has been introduced;
- the current lesson is the first one that is not done;
- one new topic per day: the current lesson can start only if no other topic
  had words introduced today (`introduced_on`);
- done lessons of today's topic can be replayed as often as the child likes;
- older words come back only as review steps mixed into any session.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, Word, WordProgress

MAX_WORDS_PER_LESSON = 10

LessonStatus = Literal["done", "current", "locked"]


@dataclass(frozen=True)
class Lesson:
    number: int  # 1-based, across all topics
    topic: Topic
    part: int  # 1-based within the topic
    parts: int
    words: tuple[Word, ...]  # in learning order


def part_sizes(count: int, max_size: int = MAX_WORDS_PER_LESSON) -> list[int]:
    """Equal parts, largest first: 12 words are 6+6, not 10+2."""
    parts = max(1, ceil(count / max_size))
    base, extra = divmod(count, parts)
    return [base + 1] * extra + [base] * (parts - extra)


def build_lessons(topics: Sequence[Topic], words: Sequence[Word]) -> list[Lesson]:
    """`words` must already be in learning order within each topic."""
    lessons: list[Lesson] = []
    for topic in sorted(topics, key=lambda t: t.order):
        topic_words = [w for w in words if w.topic_id == topic.id]
        sizes = part_sizes(len(topic_words))
        start = 0
        for part, size in enumerate(sizes, 1):
            lessons.append(
                Lesson(
                    number=len(lessons) + 1,
                    topic=topic,
                    part=part,
                    parts=len(sizes),
                    words=tuple(topic_words[start : start + size]),
                )
            )
            start += size
    return lessons


async def load_lessons(db: AsyncSession) -> list[Lesson]:
    topics = list((await db.execute(select(Topic).order_by(Topic.order))).scalars())
    words = list((await db.execute(select(Word).order_by(Word.topic_id, Word.order))).scalars())
    return build_lessons(topics, words)


async def load_progress(db: AsyncSession, child_id: int) -> dict[int, WordProgress]:
    stmt = select(WordProgress).where(WordProgress.child_id == child_id)
    return {p.word_id: p for p in (await db.execute(stmt)).scalars()}


@dataclass(frozen=True)
class LessonState:
    lesson: Lesson
    introduced: int
    status: LessonStatus
    playable: bool  # a session for it may start today


@dataclass(frozen=True)
class Position:
    lessons: list[LessonState]
    current: LessonState | None  # None once every lesson is done
    today_topic_id: int | None  # the topic that had new words today, if any

    def get(self, number: int) -> LessonState | None:
        return next((s for s in self.lessons if s.lesson.number == number), None)


def position(lessons: Sequence[Lesson], progress: dict[int, WordProgress], today: date) -> Position:
    def introduced(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.introduced

    today_topic_id = next(
        (
            lesson.topic.id
            for lesson in lessons
            for w in lesson.words
            if (p := progress.get(w.id)) is not None and p.introduced_on == today
        ),
        None,
    )

    states: list[LessonState] = []
    current: LessonState | None = None
    for lesson in lessons:
        count = sum(introduced(w) for w in lesson.words)
        done = count == len(lesson.words)
        if done:
            status: LessonStatus = "done"
            playable = lesson.topic.id == today_topic_id
        elif current is None:
            status = "current"
            playable = today_topic_id in (None, lesson.topic.id)
        else:
            status = "locked"
            playable = False
        state = LessonState(lesson=lesson, introduced=count, status=status, playable=playable)
        if status == "current":
            current = state
        states.append(state)
    return Position(lessons=states, current=current, today_topic_id=today_topic_id)
