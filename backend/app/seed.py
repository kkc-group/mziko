"""Load topics and words from content/topics/*.yaml into the database.

Idempotent: upserts by `topic.slug` and `(topic, word.slug)`. Words removed from
a YAML file are left in the database so that children's progress is never lost.

Usage: `python -m app.seed [content_dir]`
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import ImageKind, Topic, Word


class ImageSpec(BaseModel):
    kind: ImageKind
    value: str


class WordSpec(BaseModel):
    slug: str
    ka: str
    tr: str
    ru: str
    image: ImageSpec


class TopicSpec(BaseModel):
    slug: str
    title_ru: str
    title_ka: str
    icon: str
    order: int
    words: list[WordSpec] = Field(min_length=1)


def load_topics(content_dir: Path) -> list[TopicSpec]:
    files = sorted((content_dir / "topics").glob("*.yaml"))
    topics: list[TopicSpec] = []
    for path in files:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        topics.append(TopicSpec.model_validate(raw))
    return topics


async def seed_topics(session: AsyncSession, topics: list[TopicSpec]) -> tuple[int, int]:
    """Upsert everything; returns (topics, words) counts written."""
    n_words = 0
    for spec in topics:
        topic_stmt = (
            insert(Topic)
            .values(
                slug=spec.slug,
                title_ru=spec.title_ru,
                title_ka=spec.title_ka,
                icon=spec.icon,
                order=spec.order,
            )
            .on_conflict_do_update(
                index_elements=[Topic.slug],
                set_={
                    "title_ru": spec.title_ru,
                    "title_ka": spec.title_ka,
                    "icon": spec.icon,
                    "order": spec.order,
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
