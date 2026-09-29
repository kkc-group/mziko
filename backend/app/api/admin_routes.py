"""Read-only routes for the back office under /api/admin."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminService, Db, Now
from app.api.parent_routes import week_brief
from app.core.clock import local_date
from app.core.config import get_settings
from app.schemas.admin import (
    ChildCard,
    ChildSummary,
    DeviceRow,
    ParentCard,
    ParentRow,
    StudyDayOut,
    TopicProgressBrief,
)
from app.services import admin, coins
from app.services.admin import ChildCard as ChildOverviewCard
from app.services.admin import ChildOverview, ParentOverview

router = APIRouter()


def child_summary(c: ChildOverview) -> ChildSummary:
    return ChildSummary(
        id=c.child.id,
        name=c.child.name,
        learned_words=c.learned_words,
        last_study_date=c.last_study_date,
        this_week=week_brief(c.this_week, c.child) if c.this_week else None,
        last_week=week_brief(c.last_week, c.child) if c.last_week else None,
        cap_reached=c.this_week is not None and c.this_week.coins >= coins.max_coins(c.child),
    )


def parent_row(p: ParentOverview) -> ParentRow:
    return ParentRow(
        id=p.parent.id,
        telegram_id=p.parent.telegram_id,
        name=p.parent.name,
        created_at=p.parent.created_at,
        last_study_date=p.last_study_date,
        children=[child_summary(c) for c in p.children],
    )


@router.get("/parents", response_model=list[ParentRow])
async def parents(db: Db, now: Now, _: AdminService) -> list[ParentRow]:
    return [parent_row(p) for p in await admin.parents_overview(db, local_date(now))]


def child_card(c: ChildOverviewCard) -> ChildCard:
    child = c.child
    code = f"{child.code_word}-{child.code_pin}" if child.code_word and child.code_pin else None
    return ChildCard(
        id=child.id,
        name=child.name,
        created_at=child.created_at,
        code=code,
        login_url=f"{get_settings().public_url.rstrip('/')}/c/{code}" if code else None,
        rate=child.rate,
        cap_lari=child.cap_lari,
        show_hint=child.show_hint,
        learned_words=c.learned_words,
        topics=[
            TopicProgressBrief(
                slug=t.topic.slug,
                icon=t.topic.icon,
                title_ru=t.topic.title_ru,
                learned=t.learned,
                total=len(t.words),
                started=any(w.id in c.introduced for w, _, _ in t.words),
            )
            for t in c.topics
        ],
        study_days=[StudyDayOut(day=d.day, finished=d.finished) for d in c.study_days],
        first_try_pct=c.first_try_pct,
        weeks=[week_brief(w, child) for w in c.weeks],
        devices=[
            DeviceRow(
                id=d.id,
                name=d.name,
                created_at=d.created_at,
                last_seen_at=d.last_seen_at,
                revoked_at=d.revoked_at,
            )
            for d in c.devices
        ],
    )


@router.get("/parents/{parent_id}", response_model=ParentCard)
async def parent(parent_id: int, db: Db, now: Now, _: AdminService) -> ParentCard:
    card = await admin.parent_card(db, parent_id, local_date(now))
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such parent")
    return ParentCard(
        id=card.parent.id,
        telegram_id=card.parent.telegram_id,
        name=card.parent.name,
        created_at=card.parent.created_at,
        children=[child_card(c) for c in card.children],
    )
