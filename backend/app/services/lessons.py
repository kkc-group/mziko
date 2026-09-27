"""Lessons: topics cut into equal parts of at most MAX_WORDS_PER_LESSON words, numbered in order.

Nothing about lessons is stored. They are derived from topic order and word
order, and a child's position from word progress and today's sessions:

- topics fall into three sections (letters, syllables, words), by slug;
- a lesson is done when every word in it has been introduced;
- within a topic lessons go in order: the first one not done is current,
  the ones after it wait for it;
- a day has one topic per section: the first session of a topic today (a new
  lesson or a replay) makes it the section's topic of the day and locks the
  other topics of that section until tomorrow;
- done lessons of an open topic can be replayed as often as the child likes;
- older words come back only as review steps mixed into any session.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session, Topic, Word, WordProgress

MAX_WORDS_PER_LESSON = 10

Section = Literal["letters", "syllables", "words"]
TopicStatus = Literal["open", "today", "locked"]
LessonStatus = Literal["done", "current", "locked"]


def section_of(topic: Topic) -> Section:
    if topic.slug.startswith("letters-"):
        return "letters"
    if topic.slug == "syllables":
        return "syllables"
    return "words"


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


async def load_today_topics(db: AsyncSession, child_id: int, today: date) -> list[int]:
    """Ids of the topics the child had sessions in today, in session order, last chosen last."""
    stmt = (
        select(Session.topic_id)
        .where(
            Session.child_id == child_id,
            Session.study_date == today,
            Session.topic_id.is_not(None),
        )
        .order_by(Session.created_at)
    )
    ordered: list[int] = []
    for topic_id in (await db.execute(stmt)).scalars():
        if topic_id is None:  # filtered above; keeps the type checker honest
            continue
        if topic_id in ordered:
            ordered.remove(topic_id)
        ordered.append(topic_id)
    return ordered


@dataclass(frozen=True)
class TopicState:
    topic: Topic
    section: Section
    status: TopicStatus
    done: bool  # every lesson of it is done


@dataclass(frozen=True)
class LessonState:
    lesson: Lesson
    introduced: int
    status: LessonStatus
    playable: bool  # a session for it may start today


@dataclass(frozen=True)
class Position:
    lessons: list[LessonState]
    topics: list[TopicState]

    def get(self, number: int) -> LessonState | None:
        return next((s for s in self.lessons if s.lesson.number == number), None)

    def lesson_of_topic(self, topic_id: int) -> LessonState | None:
        """The topic's lesson to play: its first unfinished one, else its last (a replay)."""
        mine = [s for s in self.lessons if s.lesson.topic.id == topic_id]
        if not mine:
            return None
        return next((s for s in mine if s.status != "done"), mine[-1])

    @property
    def all_done(self) -> bool:
        return all(s.status == "done" for s in self.lessons)


def position(
    lessons: Sequence[Lesson], progress: dict[int, WordProgress], today_topics: Collection[int]
) -> Position:
    """`today_topics` are the ids of the topics the child had sessions in today."""

    def introduced(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.introduced

    today_by_section: dict[Section, int] = {}
    for lesson in lessons:
        if lesson.topic.id in today_topics:
            today_by_section[section_of(lesson.topic)] = lesson.topic.id

    def topic_status(topic: Topic) -> TopicStatus:
        chosen = today_by_section.get(section_of(topic))
        if chosen is None:
            return "open"
        return "today" if chosen == topic.id else "locked"

    states: list[LessonState] = []
    topics: list[TopicState] = []
    current_of: dict[int, bool] = {}  # topic id -> its current lesson has been placed
    for lesson in lessons:
        topic = lesson.topic
        count = sum(introduced(w) for w in lesson.words)
        if count == len(lesson.words):
            status: LessonStatus = "done"
        elif not current_of.get(topic.id):
            status = "current"
            current_of[topic.id] = True
        else:
            status = "locked"
        playable = status != "locked" and topic_status(topic) != "locked"
        states.append(LessonState(lesson, introduced=count, status=status, playable=playable))
        if lesson.part == lesson.parts:
            done = all(s.status == "done" for s in states if s.lesson.topic.id == topic.id)
            topics.append(
                TopicState(
                    topic=topic, section=section_of(topic), status=topic_status(topic), done=done
                )
            )
    return Position(lessons=states, topics=topics)
