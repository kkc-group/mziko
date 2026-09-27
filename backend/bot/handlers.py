"""Commands and inline-button callbacks. Every child access goes through the parent link."""

import logging
from collections.abc import Awaitable, Callable
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.models import Child, Device, Parent
from app.services import coins, pairing, parents, report
from bot import keyboards, texts

log = logging.getLogger(__name__)
router = Router()

ChildAction = Callable[[Message, AsyncSession, Parent, Child], Awaitable[None]]


# --- actions on one child -----------------------------------------------------


async def show_report(message: Message, db: AsyncSession, parent: Parent, child: Child) -> None:
    r = await report.week_report(db, child, clock.now())
    await message.answer(texts.report_text(r), reply_markup=keyboards.report_kb(r))


async def show_progress(message: Message, db: AsyncSession, parent: Parent, child: Child) -> None:
    await message.answer(texts.progress_text(child, await report.progress_by_topic(db, child)))


async def show_settings(message: Message, db: AsyncSession, parent: Parent, child: Child) -> None:
    await message.answer(texts.settings_text(child), reply_markup=keyboards.settings_kb(child))


async def show_pair(message: Message, db: AsyncSession, parent: Parent, child: Child) -> None:
    code = await pairing.create_pair_code(db, parent, child, clock.now())
    url = f"{get_settings().public_url.rstrip('/')}/pair/{code.code}"
    await message.answer(texts.pair_text(child, url))


async def show_devices(message: Message, db: AsyncSession, parent: Parent, child: Child) -> None:
    devices = await pairing.active_devices(db, child.id)
    await message.answer(
        texts.devices_text(child, devices),
        reply_markup=keyboards.devices_kb(devices) if devices else None,
    )


ACTIONS: dict[str, ChildAction] = {
    "report": show_report,
    "progress": show_progress,
    "settings": show_settings,
    "pair": show_pair,
    "devices": show_devices,
}


async def run_for_child(action: str, message: Message, db: AsyncSession, parent: Parent) -> None:
    """Run the action directly for an only child, or ask which child first."""
    children = await parents.children_of(db, parent)
    if not children:
        await message.answer("Сначала добавьте ребёнка: /addchild Имя")
    elif len(children) == 1:
        await ACTIONS[action](message, db, parent, children[0])
    else:
        await message.answer("Кто?", reply_markup=keyboards.children_kb(children, action))


# --- commands -----------------------------------------------------------------


@router.message(Command("start", "help"))
async def cmd_start(message: Message, db: AsyncSession, parent: Parent) -> None:
    await message.answer(texts.start_text(await parents.children_of(db, parent)))


@router.message(Command("addchild"))
async def cmd_addchild(
    message: Message, command: CommandObject, db: AsyncSession, parent: Parent
) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Напишите имя: /addchild Сандро")
        return
    child = await parents.create_child(db, parent, name)
    await message.answer(f"Добавил: {escape(child.name)}. Привязать устройство: /pair")


async def cmd_action(
    message: Message, db: AsyncSession, parent: Parent, command: CommandObject
) -> None:
    await run_for_child(command.command, message, db, parent)


router.message.register(cmd_action, Command(*ACTIONS))


# --- callbacks ----------------------------------------------------------------


def _message_of(callback: CallbackQuery) -> Message | None:
    return callback.message if isinstance(callback.message, Message) else None


async def _edit(message: Message, text: str, kb: InlineKeyboardMarkup | None) -> None:
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:  # "message is not modified" and the like
        log.debug("edit skipped: %s", exc)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("child:"))
async def cb_child(callback: CallbackQuery, db: AsyncSession, parent: Parent) -> None:
    _, action, child_id = (callback.data or "").split(":")
    message = _message_of(callback)
    child = await parents.child_of_parent(db, parent, int(child_id))
    if message is None or child is None or action not in ACTIONS:
        await callback.answer("Недоступно")
        return
    await callback.answer()
    await ACTIONS[action](message, db, parent, child)


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(callback: CallbackQuery, db: AsyncSession, parent: Parent) -> None:
    week = await report.week_by_id(db, int((callback.data or "").split(":")[1]))
    child = await parents.child_of_parent(db, parent, week.child_id) if week else None
    message = _message_of(callback)
    if week is None or child is None:
        await callback.answer("Недоступно")
        return
    already_paid = week.status.value == "paid"
    now = clock.now()
    await coins.pay_week(db, week, child, now)
    await callback.answer(
        f"Уже было выплачено: {texts.lari(week.lari_paid or 0)}"
        if already_paid
        else f"Выплачено {texts.lari(week.lari_paid or 0)}"
    )
    if message is not None:
        r = await report.week_report(db, child, now, start=week.week_start)
        await _edit(message, texts.report_text(r), keyboards.report_kb(r))


@router.callback_query(F.data.startswith("words:"))
async def cb_words(callback: CallbackQuery, db: AsyncSession, parent: Parent) -> None:
    week = await report.week_by_id(db, int((callback.data or "").split(":")[1]))
    child = await parents.child_of_parent(db, parent, week.child_id) if week else None
    message = _message_of(callback)
    if week is None or child is None or message is None:
        await callback.answer("Недоступно")
        return
    await callback.answer()
    words = await report.learned_in_week(db, child.id, week.week_start)
    await message.answer(texts.words_of_week_text(child, words))


@router.callback_query(F.data.startswith("set:"))
async def cb_settings(callback: CallbackQuery, db: AsyncSession, parent: Parent) -> None:
    _, child_id, field, value = (callback.data or "").split(":")
    child = await parents.child_of_parent(db, parent, int(child_id))
    message = _message_of(callback)
    if child is None or message is None:
        await callback.answer("Недоступно")
        return
    if field == "rate":
        await parents.update_settings(db, child, rate=int(value))
    elif field == "cap":
        await parents.update_settings(db, child, cap_lari=int(value))
    elif field == "hint":
        await parents.update_settings(db, child, show_hint=not child.show_hint)
    await callback.answer("Сохранено")
    await _edit(message, texts.settings_text(child), keyboards.settings_kb(child))


@router.callback_query(F.data.startswith("dev:"))
async def cb_device(callback: CallbackQuery, db: AsyncSession, parent: Parent) -> None:
    device = await db.get(Device, int((callback.data or "").split(":")[1]))
    child = await parents.child_of_parent(db, parent, device.child_id) if device else None
    message = _message_of(callback)
    if device is None or child is None or message is None:
        await callback.answer("Недоступно")
        return
    await pairing.revoke_device(db, device.id, clock.now())
    await callback.answer("Устройство отключено")
    devices = await pairing.active_devices(db, child.id)
    await _edit(
        message,
        texts.devices_text(child, devices),
        keyboards.devices_kb(devices) if devices else None,
    )
