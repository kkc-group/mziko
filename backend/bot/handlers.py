"""Commands and inline-button callbacks. Every call goes to the API as the sending parent."""

import logging
from collections.abc import Awaitable, Callable
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.schemas.parent import ChildInfo
from bot import keyboards, texts
from bot.api import ParentApi

log = logging.getLogger(__name__)
router = Router()

ChildAction = Callable[[Message, ParentApi, ChildInfo], Awaitable[None]]


# --- actions on one child -----------------------------------------------------


async def show_report(message: Message, api: ParentApi, child: ChildInfo) -> None:
    r = await api.report(child.id)
    await message.answer(texts.report_text(r), reply_markup=keyboards.report_kb(r))


async def show_progress(message: Message, api: ParentApi, child: ChildInfo) -> None:
    p = await api.progress(child.id)
    await message.answer(texts.progress_text(p.child, p.topics))


async def show_settings(message: Message, api: ParentApi, child: ChildInfo) -> None:
    await message.answer(texts.settings_text(child), reply_markup=keyboards.settings_kb(child))


async def show_pair(message: Message, api: ParentApi, child: ChildInfo) -> None:
    code = await api.pair_code(child.id)
    await message.answer(texts.pair_text(child, code.url))


async def show_devices(message: Message, api: ParentApi, child: ChildInfo) -> None:
    devices = await api.devices(child.id)
    await message.answer(
        texts.devices_text(child, devices),
        reply_markup=keyboards.devices_kb(child, devices) if devices else None,
    )


ACTIONS: dict[str, ChildAction] = {
    "report": show_report,
    "progress": show_progress,
    "settings": show_settings,
    "pair": show_pair,
    "devices": show_devices,
}


async def run_for_child(action: str, message: Message, api: ParentApi) -> None:
    """Run the action directly for an only child, or ask which child first."""
    children = await api.children()
    if not children:
        await message.answer("Сначала добавьте ребёнка: /addchild Имя")
    elif len(children) == 1:
        await ACTIONS[action](message, api, children[0])
    else:
        await message.answer("Кто?", reply_markup=keyboards.children_kb(children, action))


# --- commands -----------------------------------------------------------------


@router.message(Command("start", "help"))
async def cmd_start(message: Message, api: ParentApi) -> None:
    await message.answer(texts.start_text(await api.children()))


@router.message(Command("addchild"))
async def cmd_addchild(message: Message, command: CommandObject, api: ParentApi) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Напишите имя: /addchild Сандро")
        return
    child = await api.add_child(name)
    await message.answer(f"Добавил: {escape(child.name)}. Привязать устройство: /pair")


async def cmd_action(message: Message, api: ParentApi, command: CommandObject) -> None:
    await run_for_child(command.command, message, api)


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
async def cb_child(callback: CallbackQuery, api: ParentApi) -> None:
    _, action, child_id = (callback.data or "").split(":")
    message = _message_of(callback)
    child = await api.child(int(child_id))
    if message is None or child is None or action not in ACTIONS:
        await callback.answer("Недоступно")
        return
    await callback.answer()
    await ACTIONS[action](message, api, child)


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(callback: CallbackQuery, api: ParentApi) -> None:
    paid = await api.pay(int((callback.data or "").split(":")[1]))
    amount = texts.lari(paid.report.week.lari_paid or 0)
    await callback.answer(
        f"Уже было выплачено: {amount}" if paid.already_paid else f"Выплачено {amount}"
    )
    message = _message_of(callback)
    if message is not None:
        await _edit(message, texts.report_text(paid.report), keyboards.report_kb(paid.report))


@router.callback_query(F.data.startswith("words:"))
async def cb_words(callback: CallbackQuery, api: ParentApi) -> None:
    r = await api.week(int((callback.data or "").split(":")[1]))
    message = _message_of(callback)
    if message is None:
        await callback.answer("Недоступно")
        return
    await callback.answer()
    await message.answer(texts.words_of_week_text(r.child, r.learned))


@router.callback_query(F.data.startswith("set:"))
async def cb_settings(callback: CallbackQuery, api: ParentApi) -> None:
    _, child_id, field, value = (callback.data or "").split(":")
    message = _message_of(callback)
    if message is None:
        await callback.answer("Недоступно")
        return
    if field == "rate":
        child = await api.update_settings(int(child_id), rate=int(value))
    elif field == "cap":
        child = await api.update_settings(int(child_id), cap_lari=int(value))
    elif field == "hint":
        child = await api.update_settings(int(child_id), show_hint=value == "1")
    else:
        await callback.answer("Недоступно")
        return
    await callback.answer("Сохранено")
    await _edit(message, texts.settings_text(child), keyboards.settings_kb(child))


@router.callback_query(F.data.startswith("dev:"))
async def cb_device(callback: CallbackQuery, api: ParentApi) -> None:
    _, child_id, device_id = (callback.data or "").split(":")
    message = _message_of(callback)
    child = await api.child(int(child_id))
    if message is None or child is None:
        await callback.answer("Недоступно")
        return
    devices = await api.revoke_device(child.id, int(device_id))
    await callback.answer("Устройство отключено")
    await _edit(
        message,
        texts.devices_text(child, devices),
        keyboards.devices_kb(child, devices) if devices else None,
    )
