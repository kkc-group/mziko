"""Load topics and words from content/topics/*.yaml into the database.

The order of topics is the order of their slugs in content/order.yaml.

Idempotent: upserts by `topic.slug` and `(topic, word.slug)`. Words removed from
a YAML file are left in the database so that children's progress is never lost.

Usage: `python -m app.seed [content_dir]`
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import ImageKind, Topic, Word

# Longest run of letters a text card can show without breaking the answer tile grid
# (see docs/mockups/letter-cards.html). Text may wrap at spaces, never inside a word.
TEXT_CHUNK_MAX = 10


class ImageSpec(BaseModel):
    kind: ImageKind
    value: str

    @model_validator(mode="after")
    def text_fits_a_tile(self) -> "ImageSpec":
        if self.kind is ImageKind.text:
            too_long = [c for c in self.value.split() if len(c) > TEXT_CHUNK_MAX]
            if too_long:
                raise ValueError(
                    f"text image {self.value!r}: {too_long} longer than {TEXT_CHUNK_MAX} letters"
                )
        return self


class AnchorSpec(BaseModel):
    """Example word for a letter: shown as "⚽ ბურთი" under the letter on the intro card."""

    ka: str
    tr: str
    ru: str
    emoji: str | None = None


class WordSpec(BaseModel):
    slug: str
    ka: str
    tr: str
    ru: str
    image: ImageSpec
    anchor: AnchorSpec | None = None


class StoryLineSpec(BaseModel):
    """One line of a story: one screen with a scene picture, heard as `line-<n>.mp3`."""

    ka: str
    tr: str
    ru: str
    scene: str  # URL of the picture, /media/scenes/<topic>/<file>


class QuestionSpec(BaseModel):
    """Listen and find on a story line: the line is heard, the child picks `answer`.

    Words are referenced as "<topic slug>/<word slug>" and may come from any topic.
    """

    line: int = Field(ge=1)  # 1-based number of the line that is played
    answer: str
    options: list[str] = Field(min_length=1)  # the wrong options


class StorySpec(BaseModel):
    lines: list[StoryLineSpec] = Field(min_length=1)
    questions: list[QuestionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def questions_point_at_lines(self) -> "StorySpec":
        for q in self.questions:
            if q.line > len(self.lines):
                raise ValueError(f"question on line {q.line}: the story has {len(self.lines)}")
            refs = [q.answer, *q.options]
            if len(set(refs)) != len(refs):
                raise ValueError(f"question on line {q.line}: repeated option {refs}")
        return self


def word_ref(ref: str) -> tuple[str, str]:
    """Split "colors/yellow" into ("colors", "yellow")."""
    topic, _, word = ref.partition("/")
    if not topic or not word:
        raise ValueError(f"word reference {ref!r} is not <topic>/<word>")
    return topic, word


class TopicSpec(BaseModel):
    slug: str
    title_ru: str
    title_ka: str
    icon: str
    order: int = 0  # not in the topic file: load_topics sets it from the place in order.yaml
    story: StorySpec | None = None
    words: list[WordSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def words_are_distinguishable(self) -> "TopicSpec":
        # Quiz distractors come from the same topic: two words sharing a picture (or a
        # slug) would make "listen and find" unanswerable.
        for field in ("slug", "ka"):
            values = [getattr(w, field) for w in self.words]
            dups = sorted({v for v in values if values.count(v) > 1})
            if dups:
                raise ValueError(f"topic {self.slug!r}: duplicate {field} {dups}")
        pictures = [w.image.value for w in self.words]
        dups = sorted({p for p in pictures if pictures.count(p) > 1})
        if dups:
            raise ValueError(f"topic {self.slug!r}: several words share the picture {dups}")
        # A story line is sent as a word called line-<n> (its audio is line-<n>.mp3).
        if self.story is not None:
            clash = [w.slug for w in self.words if w.slug.startswith("line-")]
            if clash:
                raise ValueError(f"topic {self.slug!r}: word slugs {clash} are kept for lines")
        return self


def load_topics(content_dir: Path) -> list[TopicSpec]:
    """Topics in path order: `order.yaml` lists the slugs, a topic's place there is its order."""
    by_slug: dict[str, TopicSpec] = {}
    for path in sorted((content_dir / "topics").glob("*.yaml")):
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        spec = TopicSpec.model_validate(raw)
        by_slug[spec.slug] = spec

    slugs: list[str] = yaml.safe_load((content_dir / "order.yaml").read_text(encoding="utf-8"))
    repeated = sorted({s for s in slugs if slugs.count(s) > 1})
    missing = sorted(by_slug.keys() - set(slugs))
    unknown = sorted(set(slugs) - by_slug.keys())
    if repeated or missing or unknown:
        raise ValueError(
            f"order.yaml: listed twice {repeated}, not listed {missing}, no such topic {unknown}"
        )
    for index, slug in enumerate(slugs):
        by_slug[slug].order = (index + 1) * 10

    # Story questions may use words of any topic; each must exist, and the options
    # of one question must look and sound different.
    words = {(t.slug, w.slug): w for t in by_slug.values() for w in t.words}
    for topic in by_slug.values():
        for q in topic.story.questions if topic.story else []:
            refs = [word_ref(r) for r in (q.answer, *q.options)]
            unknown_refs = [f"{t}/{w}" for t, w in refs if (t, w) not in words]
            if unknown_refs:
                raise ValueError(f"topic {topic.slug!r}: no such words {unknown_refs}")
            options = [words[r] for r in refs]
            for field in ("slug", "ka"):
                values = [getattr(w, field) for w in options]
                if len(set(values)) != len(values):
                    raise ValueError(f"topic {topic.slug!r}: question {q.line} repeats a {field}")
            if len({w.image.value for w in options}) != len(options):
                raise ValueError(f"topic {topic.slug!r}: question {q.line} repeats a picture")
    return [by_slug[slug] for slug in slugs]


async def seed_topics(session: AsyncSession, topics: list[TopicSpec]) -> tuple[int, int]:
    """Upsert everything; returns (topics, words) counts written."""
    n_words = 0
    for spec in topics:
        story = spec.story.model_dump() if spec.story else None
        topic_stmt = (
            insert(Topic)
            .values(
                slug=spec.slug,
                title_ru=spec.title_ru,
                title_ka=spec.title_ka,
                icon=spec.icon,
                order=spec.order,
                story=story,
            )
            .on_conflict_do_update(
                index_elements=[Topic.slug],
                set_={
                    "title_ru": spec.title_ru,
                    "title_ka": spec.title_ka,
                    "icon": spec.icon,
                    "order": spec.order,
                    "story": story,
                },
            )
            .returning(Topic.id)
        )
        topic_id = (await session.execute(topic_stmt)).scalar_one()

        for position, word in enumerate(spec.words):
            word_stmt = insert(Word).values(
                topic_id=topic_id,
                slug=word.slug,
                ka=word.ka,
                tr=word.tr,
                ru=word.ru,
                image_kind=word.image.kind,
                image_value=word.image.value,
                anchor=word.anchor.model_dump() if word.anchor else None,
                order=position,
            )
            word_stmt = word_stmt.on_conflict_do_update(
                index_elements=[Word.topic_id, Word.slug],
                set_={
                    "ka": word.ka,
                    "tr": word.tr,
                    "ru": word.ru,
                    "image_kind": word.image.kind,
                    "image_value": word.image.value,
                    "anchor": word.anchor.model_dump() if word.anchor else None,
                    "order": position,
                },
            )
            await session.execute(word_stmt)
            n_words += 1
    await session.commit()
    return len(topics), n_words


async def main(content_dir: Path) -> None:
    topics = load_topics(content_dir)
    async with get_sessionmaker()() as session:
        n_topics, n_words = await seed_topics(session, topics)
        total = (await session.execute(select(Word.id))).all()
    print(f"seeded {n_topics} topics, {n_words} words ({len(total)} words in db)")


if __name__ == "__main__":
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().content_dir
    asyncio.run(main(directory))
