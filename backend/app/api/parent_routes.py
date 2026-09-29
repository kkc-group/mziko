"""Routes for the Telegram bot under /api/parent: everything a parent does goes through here."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BotService, CurrentParent, Db, Now, TelegramId
from app.core.config import get_settings
from app.models import Child, Device, ImageKind, Parent, Week, Word
from app.schemas.parent import (
    ChildAttach,
    ChildCodeOut,
    ChildCreate,
    ChildInfo,
    DeviceOut,
    DueReportOut,
    ParentOut,
    ParentRegister,
    PayOut,
    ProgressOut,
    SettingsPatch,
    TopicProgressOut,
    WeekBrief,
    WeekReportOut,
    WordBrief,
    WordProgressOut,
)
from app.services import coins, lessons, login_codes, pairing, parents, report
from app.services.report import TopicProgress, WeekReport

router = APIRouter()


# --- ORM → wire ---------------------------------------------------------------


def child_info(child: Child) -> ChildInfo:
    return ChildInfo(
        id=child.id,
        name=child.name,
        rate=child.rate,
        cap_lari=child.cap_lari,
        show_hint=child.show_hint,
    )


def word_brief(word: Word) -> WordBrief:
    icon = word.image_value if word.image_kind is ImageKind.emoji else word.ka
    return WordBrief(ka=word.ka, tr=word.tr, ru=word.ru, icon=icon)


def week_brief(week: Week, child: Child) -> WeekBrief:
    return WeekBrief(
        id=week.id,
        week_start=week.week_start,
        week_end=week.week_start + timedelta(days=6),
        coins=week.coins,
        status=week.status.value,
        lari_due=coins.lari_for(week.coins, child.rate, child.cap_lari),
        lari_paid=week.lari_paid,
        paid_at=week.paid_at,
    )


def report_out(r: WeekReport) -> WeekReportOut:
    return WeekReportOut(
        child=child_info(r.child),
        week=week_brief(r.week, r.child),
        days_studied=r.days_studied,
        learned=[word_brief(w) for w in r.learned],
        cap_reached=r.cap_reached,
        unpaid_past=[week_brief(w, r.child) for w in r.unpaid_past],
    )


def topic_progress_out(tp: TopicProgress) -> TopicProgressOut:
    return TopicProgressOut(
        slug=tp.topic.slug,
        section=lessons.section_of(tp.topic),
        icon=tp.topic.icon,
        title_ru=tp.topic.title_ru,
        learned=tp.learned,
        total=len(tp.words),
        words=[
            WordProgressOut(ka=w.ka, ru=w.ru, stage=stage, last_correct_date=last)
            for w, stage, last in tp.words
        ],
    )


def device_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
    )


def child_code_out(child: Child) -> ChildCodeOut:
    code = f"{child.code_word}-{child.code_pin}"
    return ChildCodeOut(
        word=child.code_word or "",
        pin=child.code_pin or "",
        code=code,
        url=f"{get_settings().public_url.rstrip('/')}/c/{code}",
    )


# --- access -------------------------------------------------------------------


async def own_child(db: Db, parent: CurrentParent, child_id: int) -> Child:
    child = await parents.child_of_parent(db, parent, child_id)
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such child")
    return child


async def own_week(db: Db, parent: CurrentParent, week_id: int) -> tuple[Week, Child]:
    """A week only through the parent link; a stranger's week looks like a missing one."""
    week = await report.week_by_id(db, week_id)
    child = await parents.child_of_parent(db, parent, week.child_id) if week else None
    if week is None or child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such week")
    return week, child


# --- routes -------------------------------------------------------------------


@router.get("/children/{child_id}/report", response_model=WeekReportOut)
async def child_report(
    child_id: int, db: Db, now: Now, parent: CurrentParent, week_start: date | None = None
) -> WeekReportOut:
    """The current week (or the week beginning at `week_start`) of one child."""
    child = await own_child(db, parent, child_id)
    return report_out(await report.week_report(db, child, now, start=week_start))


@router.get("/weeks/{week_id}", response_model=WeekReportOut)
async def week(week_id: int, db: Db, now: Now, parent: CurrentParent) -> WeekReportOut:
    """Report for a week the bot already holds an id of (from a button)."""
    week, child = await own_week(db, parent, week_id)
    return report_out(await report.week_report(db, child, now, start=week.week_start))


@router.post("/weeks/{week_id}/pay", response_model=PayOut)
async def pay(week_id: int, db: Db, now: Now, parent: CurrentParent) -> PayOut:
    """Close the week as paid in cash. Idempotent: paying twice reports `already_paid`."""
    week, child = await own_week(db, parent, week_id)
    already_paid = week.status.value == "paid"
    await coins.pay_week(db, week, child, now)
    r = await report.week_report(db, child, now, start=week.week_start)
    return PayOut(already_paid=already_paid, report=report_out(r))


async def parent_out(db: Db, parent: Parent) -> ParentOut:
    return ParentOut(
        telegram_id=parent.telegram_id,
        name=parent.name,
        children=[child_info(c) for c in await parents.children_of(db, parent)],
    )


@router.get("/me", response_model=ParentOut)
async def me(db: Db, telegram_id: TelegramId) -> ParentOut:
    """Who the bot is talking to; 404 (not 403) for a stranger, so the wizard can start."""
    parent = await parents.get_parent(db, telegram_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not registered")
    return await parent_out(db, parent)


@router.put("/me", response_model=ParentOut)
async def register(body: ParentRegister, db: Db, telegram_id: TelegramId) -> ParentOut:
    """Step one of the wizard: create the parent with a name, or rename them."""
    return await parent_out(db, await parents.register(db, telegram_id, body.name))


@router.get("/children", response_model=list[ChildInfo])
async def children(db: Db, parent: CurrentParent) -> list[ChildInfo]:
    return [child_info(c) for c in await parents.children_of(db, parent)]


@router.post("/children", response_model=ChildInfo)
async def add_child(body: ChildCreate, db: Db, parent: CurrentParent) -> ChildInfo:
    return child_info(await parents.create_child(db, parent, body.name))


@router.post("/children/attach", response_model=ChildInfo)
async def attach_child(body: ChildAttach, db: Db, parent: CurrentParent) -> ChildInfo:
    """Link an existing child by its login code; an unknown code is 404."""
    child = await parents.attach_child_by_code(db, parent, body.code)
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no child with this code")
    return child_info(child)


@router.delete("/children/{child_id}", response_model=list[ChildInfo])
async def detach_child(child_id: int, db: Db, parent: CurrentParent) -> list[ChildInfo]:
    """Unlink the child from this parent; returns the remaining children."""
    child = await own_child(db, parent, child_id)
    await parents.detach_child(db, parent, child)
    return [child_info(c) for c in await parents.children_of(db, parent)]


@router.post("/children/{child_id}/reset", response_model=ChildInfo)
async def reset_progress(child_id: int, db: Db, parent: CurrentParent) -> ChildInfo:
    """Wipe learned words, sessions, weeks and coins; settings, code and devices stay."""
    child = await own_child(db, parent, child_id)
    await parents.reset_progress(db, child)
    return child_info(child)


@router.get("/children/{child_id}/progress", response_model=ProgressOut)
async def progress(child_id: int, db: Db, parent: CurrentParent) -> ProgressOut:
    child = await own_child(db, parent, child_id)
    topics = await report.progress_by_topic(db, child)
    return ProgressOut(child=child_info(child), topics=[topic_progress_out(t) for t in topics])


@router.patch("/children/{child_id}/settings", response_model=ChildInfo)
async def update_settings(
    child_id: int, body: SettingsPatch, db: Db, parent: CurrentParent
) -> ChildInfo:
    child = await own_child(db, parent, child_id)
    updated = await parents.update_settings(
        db,
        child,
        **body.model_dump(exclude_none=True),
    )
    return child_info(updated)


@router.get("/children/{child_id}/code", response_model=ChildCodeOut)
async def child_code(child_id: int, db: Db, now: Now, parent: CurrentParent) -> ChildCodeOut:
    """The child's permanent login code, issued on first request."""
    child = await own_child(db, parent, child_id)
    return child_code_out(await login_codes.ensure_code(db, child, now))


@router.post("/children/{child_id}/code/rotate", response_model=ChildCodeOut)
async def rotate_child_code(child_id: int, db: Db, now: Now, parent: CurrentParent) -> ChildCodeOut:
    """New pin, same word; lifts login locks stuck on that word."""
    child = await own_child(db, parent, child_id)
    return child_code_out(await login_codes.rotate_pin(db, child, now))


@router.get("/children/{child_id}/devices", response_model=list[DeviceOut])
async def devices(child_id: int, db: Db, parent: CurrentParent) -> list[DeviceOut]:
    child = await own_child(db, parent, child_id)
    return [device_out(d) for d in await pairing.active_devices(db, child.id)]


@router.delete("/children/{child_id}/devices/{device_id}", response_model=list[DeviceOut])
async def delete_device(
    child_id: int, device_id: int, db: Db, now: Now, parent: CurrentParent
) -> list[DeviceOut]:
    child = await own_child(db, parent, child_id)
    device = await db.get(Device, device_id)
    if device is None or device.child_id != child.id or device.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such device")
    await pairing.revoke_device(db, device.id, now)
    return [device_out(d) for d in await pairing.active_devices(db, child.id)]


@router.get("/reports/due", response_model=list[DueReportOut])
async def reports_due(db: Db, now: Now, _: BotService) -> list[DueReportOut]:
    """Every child's current-week report, for the bot's Sunday-evening broadcast."""
    out: list[DueReportOut] = []
    for child in await parents.all_children(db):
        r = await report.week_report(db, child, now)
        out.append(
            DueReportOut(telegram_ids=[p.telegram_id for p in child.parents], report=report_out(r))
        )
    return out
