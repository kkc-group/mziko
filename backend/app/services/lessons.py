"""Lessons: topics cut into equal parts of at most MAX_WORDS_PER_LESSON words, numbered in order.

Nothing about lessons is stored. They are derived from topic order and word
order, and a child's position from word progress and today's sessions:

- topics fall into three sections (letters, syllables, words), by slug;
- a lesson is done when every word in it has been introduced;
- within a topic lessons go in order: the first one not done is current,
  the ones after it wait for it;
- within a section topics go in order: a topic is started once it has had a
  session on any day; a started topic is never locked, so it can be replayed
  or started over at any time;
- a topic not started yet opens when the one before it in its section is done,
  and a section starts at most one new topic a day: the day a topic has its
  first session, the next one waits for tomorrow;
- a parent may overrule this for one topic: an opened topic can be started at
  once, a closed one is locked whatever its progress and does not hold up the
  topic after it;
- done lessons of an open topic can be replayed as often as the child likes;
- older words come back only as review steps mixed into any session.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import ceil
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session, Topic, TopicAccess, Word, WordProgress

MAX_WORDS_PER_LESSON = 10

Section = Literal["letters", "syllables", "words"]
TopicStatus = Literal["open", "today", "locked"]
LessonStatus = Literal["done", "current", "locked"]
AccessMode = Literal["open", "closed"]  # a parent's say on a topic; no entry is the usual order


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


async def reset_topic_progress(db: AsyncSession, child_id: int, topic_id: int) -> None:
    """Forget that the topic's words were shown, so its lessons start over from the first.

    Stages, coins and stickers stay: the child walks the words again, nothing is lost.
    Shared by the child's "start the topic over" and the parent's cabinet.
    """
    stmt = (
        select(WordProgress)
        .join(Word, Word.id == WordProgress.word_id)
        .where(WordProgress.child_id == child_id, Word.topic_id == topic_id)
    )
    for progress in (await db.execute(stmt)).scalars():
        progress.introduced = False
        progress.introduced_on = None
    await db.flush()


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


async def load_topic_first_days(db: AsyncSession, child_id: int) -> dict[int, date]:
    """Topic id -> the day of the child's first session in it, for every topic ever started.

    Sessions, not word progress: starting a topic over forgets its words were
    shown, yet the topic stays started.
    """
    stmt = (
        select(Session.topic_id, func.min(Session.study_date))
        .where(Session.child_id == child_id, Session.topic_id.is_not(None))
        .group_by(Session.topic_id)
    )
    return {
        topic_id: first_day
        for topic_id, first_day in (await db.execute(stmt)).all()
        if topic_id is not None  # filtered above; keeps the type checker honest
    }


async def load_topic_access(db: AsyncSession, child_id: int) -> dict[int, AccessMode]:
    """Topic id -> "open" or "closed" for the topics a parent has set for the child."""
    stmt = select(TopicAccess.topic_id, TopicAccess.mode).where(TopicAccess.child_id == child_id)
    return {
        topic_id: "closed" if mode == "closed" else "open"
        for topic_id, mode in (await db.execute(stmt)).all()
    }


@dataclass(frozen=True)
class TopicState:
    topic: Topic
    section: Section
    status: TopicStatus
    done: bool  # every lesson of it is done
    closed: bool = False  # locked by a parent, not by the order or the day


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
    lessons: Sequence[Lesson],
    progress: dict[int, WordProgress],
    today_topics: Collection[int],
    first_days: Mapping[int, date],
    today: date,
    access: Mapping[int, AccessMode] | None = None,
) -> Position:
    """Where the child stands today: lesson statuses and which topics may be played.

    `today_topics` are the ids of the topics the child had sessions in today,
    `first_days` maps every started topic to the day of its first session.
    A started topic is "today" if it had a session today, else "open". A topic
    not started yet is "locked" while the topic before it in its section is not
    done, or while its section has a topic first started today (one new topic
    a section a day); otherwise it is "open". A done topic is never locked.

    `access` is the parent's say, topic id -> "open" or "closed". A closed topic
    is "locked" whatever its progress, and the topic after it waits for the one
    before it instead. An opened topic not started yet is "open" past both the
    order and the day's limit; once started it is today's new topic like any other.
    """
    access = access or {}

    def introduced(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.introduced

    states: list[LessonState] = []
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
        states.append(LessonState(lesson, introduced=count, status=status, playable=False))

    done_of: dict[int, bool] = {}
    for s in states:
        done_of[s.lesson.topic.id] = done_of.get(s.lesson.topic.id, True) and s.status == "done"

    new_today: set[Section] = {
        section_of(lesson.topic) for lesson in lessons if first_days.get(lesson.topic.id) == today
    }
    topic_status: dict[int, TopicStatus] = {}
    previous_done: dict[Section, bool] = {}  # section -> the topic before this one is done
    for lesson in lessons:
        topic = lesson.topic
        section = section_of(topic)
        if lesson.part != 1:
            continue
        if access.get(topic.id) == "closed":
            topic_status[topic.id] = "locked"
            continue  # out of the queue: the next topic waits for the one before this
        if topic.id in today_topics:
            topic_status[topic.id] = "today"
        elif topic.id in first_days or done_of[topic.id]:
            topic_status[topic.id] = "open"
        elif access.get(topic.id) == "open":
            topic_status[topic.id] = "open"
        elif not previous_done.get(section, True) or section in new_today:
            topic_status[topic.id] = "locked"
        else:
            topic_status[topic.id] = "open"
        previous_done[section] = done_of[topic.id]

    states = [
        replace(s, playable=s.status != "locked" and topic_status[s.lesson.topic.id] != "locked")
        for s in states
    ]
    topics = [
        TopicState(
            topic=lesson.topic,
            section=section_of(lesson.topic),
            status=topic_status[lesson.topic.id],
            done=done_of[lesson.topic.id],
            closed=access.get(lesson.topic.id) == "closed",
        )
        for lesson in lessons
        if lesson.part == lesson.parts
    ]
    return Position(lessons=states, topics=topics)
