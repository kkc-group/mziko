from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImageKind, Topic, Word
from app.seed import TopicSpec, load_topics, seed_topics

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"


async def test_seed_loads_both_topics_and_is_idempotent(db: AsyncSession) -> None:
    topics = load_topics(CONTENT_DIR)
    assert len(topics) == len(list((CONTENT_DIR / "topics").glob("*.yaml")))
    assert [t.slug for t in sorted(topics, key=lambda t: t.order)][:6] == [
        "letters-1",
        "letters-2",
        "letters-3",
        "letters-4",
        "syllables",
        "basics",
    ]

    await seed_topics(db, topics)
    await seed_topics(db, topics)  # second run must not duplicate anything

    n_topics = (await db.execute(select(func.count(Topic.id)))).scalar_one()
    n_words = (await db.execute(select(func.count(Word.id)))).scalar_one()
    assert n_topics == len(topics)
    assert n_words == sum(len(t.words) for t in topics)

    colors = (
        (
            await db.execute(
                select(Word).join(Topic).where(Topic.slug == "colors").order_by(Word.order)
            )
        )
        .scalars()
        .all()
    )
    assert [w.slug for w in colors][:3] == ["red", "blue", "green"]
    assert all(w.image_kind is ImageKind.color for w in colors)


async def test_seed_updates_changed_fields(db: AsyncSession) -> None:
    topics = load_topics(CONTENT_DIR)
    await seed_topics(db, topics)

    basics = next(t for t in topics if t.slug == "basics")
    original = basics.words[0].ru
    basics.words[0].ru = "пёс"
    await seed_topics(db, topics)

    dog = (
        await db.execute(select(Word).join(Topic).where(Topic.slug == "basics", Word.slug == "dog"))
    ).scalar_one()
    assert dog.ru == "пёс"

    basics.words[0].ru = original
    await seed_topics(db, topics)


def test_content_has_no_repeated_words_or_topic_orders() -> None:
    """Each word is learned once: the same Georgian word must not appear in two topics."""
    topics = load_topics(CONTENT_DIR)
    orders = [t.order for t in topics]
    assert len(set(orders)) == len(orders)
    seen: dict[str, str] = {}
    for topic in topics:
        if topic.slug == "syllables":
            continue  # reading drills, not vocabulary: "მე" the syllable may equal "მე" the word
        for word in topic.words:
            assert word.ka not in seen, f"{word.ka!r} in both {seen[word.ka]} and {topic.slug}"
            seen[word.ka] = topic.slug


def test_file_pictures_exist_under_media() -> None:
    """A `file` picture is served from /media, so the path must point at a committed file."""
    for topic in load_topics(CONTENT_DIR):
        for word in topic.words:
            if word.image.kind is ImageKind.file:
                path = CONTENT_DIR.parent / word.image.value.lstrip("/")
                assert word.image.value.startswith("/media/images/"), f"{topic.slug}/{word.slug}"
                assert path.is_file(), f"{topic.slug}/{word.slug}: {word.image.value} is missing"


def letters_spec(text: str) -> dict[str, object]:
    return {
        "slug": "letters-test",
        "title_ru": "Буквы",
        "title_ka": "ასოები",
        "icon": "🔤",
        "order": 99,
        "words": [
            {
                "slug": "w",
                "ka": text,
                "tr": "?",
                "ru": "?",
                "image": {"kind": "text", "value": text},
                "anchor": {"ka": "ბურთი", "tr": "бурти", "ru": "мяч", "emoji": "⚽"},
            }
        ],
    }


def test_text_card_may_wrap_at_spaces_but_never_inside_a_word() -> None:
    spec = TopicSpec.model_validate(letters_spec("დილა მშვიდობისა"))  # 4 + 10 letters: fits
    assert spec.words[0].anchor is not None and spec.words[0].anchor.emoji == "⚽"

    with pytest.raises(ValidationError, match="longer than 10"):
        TopicSpec.model_validate(letters_spec("გამარჯობათ!!"))  # 12 chars in one chunk


async def test_seed_stores_anchor_and_text_kind(db: AsyncSession) -> None:
    spec = TopicSpec.model_validate(letters_spec("ბ"))
    await seed_topics(db, [spec])  # commits, so clean up below: other tests count topics
    try:
        word = (
            await db.execute(select(Word).join(Topic).where(Topic.slug == "letters-test"))
        ).scalar_one()
        assert word.image_kind is ImageKind.text
        assert word.anchor == {"ka": "ბურთი", "tr": "бурти", "ru": "мяч", "emoji": "⚽"}
    finally:
        await db.execute(delete(Topic).where(Topic.slug == "letters-test"))
        await db.commit()
