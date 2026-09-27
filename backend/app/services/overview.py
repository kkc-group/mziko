"""Home-screen overview for a child."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_date, week_start
from app.models import Child, Session, Topic, Word, WordProgress
from app.schemas.me import ChildOut, MeOut, SettingsOut, StickerOut, TopicOut, WeekOut
from app.services import coins
from app.services.learning import LEARNED_STAGE, word_out


async def build_me(db: AsyncSession, child: Child, now: datetime) -> MeOut:
    today = local_date(now)
    start = week_start(today)
    week = await coins.get_or_create_week(db, child.id, today)

    study_days = list(
        (
            await db.execute(
                select(Session.study_date)
                .where(
                    Session.child_id == child.id,
                    Session.finished_at.is_not(None),
                    Session.study_date >= start,
                    Session.study_date < start + timedelta(days=7),
                )
                .distinct()
                .order_by(Session.study_date)
            )
        ).scalars()
    )

    topics = list((await db.execute(select(Topic).order_by(Topic.order))).scalars())
    words = list((await db.execute(select(Word).order_by(Word.topic_id, Word.order))).scalars())
    progress = {
        p.word_id: p
        for p in (
            await db.execute(select(WordProgress).where(WordProgress.child_id == child.id))
        ).scalars()
    }

    def learned(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.stage >= LEARNED_STAGE

    def introduced(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.introduced

    review_pending = any(
        p.introduced
        and p.stage < LEARNED_STAGE
        and (p.last_correct_date is None or p.last_correct_date < today)
        for p in progress.values()
    )

    topic_slug = {t.id: t.slug for t in topics}
    topics_out = []
    for topic in topics:
        topic_words = [w for w in words if w.topic_id == topic.id]
        has_new = any(not introduced(w) for w in topic_words)
        topics_out.append(
            TopicOut(
                slug=topic.slug,
                title_ru=topic.title_ru,
                title_ka=topic.title_ka,
                icon=topic.icon,
                total=len(topic_words),
                learned=sum(learned(w) for w in topic_words),
                has_lesson=has_new or review_pending,
            )
        )

    return MeOut(
        child=ChildOut(id=child.id, name=child.name),
        settings=SettingsOut(rate=child.rate, cap_lari=child.cap_lari, show_hint=child.show_hint),
        week=WeekOut(
            week_start=start,
            today=today,
            coins=week.coins,
            lari=coins.lari_for(week.coins, child.rate, child.cap_lari),
            study_days=study_days,
        ),
        topics=topics_out,
        stickers=[
            StickerOut(word=word_out(w, topic_slug[w.topic_id]), learned=learned(w)) for w in words
        ],
    )
