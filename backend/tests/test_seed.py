from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImageKind, Topic, Word
from app.seed import load_topics, seed_topics

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"


async def test_seed_loads_both_topics_and_is_idempotent(db: AsyncSession) -> None:
    topics = load_topics(CONTENT_DIR)
    assert [t.slug for t in topics] == ["basics", "colors"]

    await seed_topics(db, topics)
    await seed_topics(db, topics)  # second run must not duplicate anything

    n_topics = (await db.execute(select(func.count(Topic.id)))).scalar_one()
    n_words = (await db.execute(select(func.count(Word.id)))).scalar_one()
    assert n_topics == 2
    assert n_words == 22

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
