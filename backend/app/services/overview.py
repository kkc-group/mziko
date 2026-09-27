"""Home-screen overview for a child."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_date, week_start
from app.models import Child, Session, Word
from app.schemas.me import (
    ChildOut,
    LessonOut,
    MeOut,
    SettingsOut,
    StickerOut,
    TopicOut,
    WeekOut,
)
from app.services import coins, lessons
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

    path = await lessons.load_lessons(db)
    progress = await lessons.load_progress(db, child.id)
    today_topics = await lessons.load_today_topics(db, child.id, today)
    position = lessons.position(path, progress, today_topics)
    today_lesson = position.lesson_of_topic(today_topics[-1]) if today_topics else None

    def learned(word: Word) -> bool:
        p = progress.get(word.id)
        return p is not None and p.stage >= LEARNED_STAGE

    review_available = any(
        p.introduced
        and p.stage < LEARNED_STAGE
        and (p.last_correct_date is None or p.last_correct_date < today)
        for p in progress.values()
    )

    lessons_out = [
        LessonOut(
            number=s.lesson.number,
            topic_slug=s.lesson.topic.slug,
            title_ru=s.lesson.topic.title_ru,
            icon=s.lesson.topic.icon,
            part=s.lesson.part,
            parts=s.lesson.parts,
            total=len(s.lesson.words),
            introduced=s.introduced,
            status=s.status,
            playable=s.playable,
        )
        for s in position.lessons
    ]
    topics_out = [
        TopicOut(
            slug=t.topic.slug,
            title_ru=t.topic.title_ru,
            icon=t.topic.icon,
            section=t.section,
            status=t.status,
            done=t.done,
        )
        for t in position.topics
    ]

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
        lessons=lessons_out,
        topics=topics_out,
        today_lesson=today_lesson.lesson.number if today_lesson else None,
        review_available=review_available,
        stickers=[
            StickerOut(word=word_out(w, lesson.topic.slug), learned=learned(w))
            for lesson in path
            for w in lesson.words
        ],
    )
