"""Commands and inline-button callbacks. Every call goes to the API as the sending parent."""

import logging
from collections.abc import Awaitable, Callable
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core.config import get_settings
from app.schemas.parent import ChildInfo, ParentOut
from bot import keyboards, texts
from bot.api import ApiError, ParentApi
from bot.registration import Step, check_name, normalize_code, suggested_name

log = logging.getLogger(__name__)
router = Router()

ChildAction = Callable[[Message, ParentApi, ChildInfo], Awaitable[None]]


# --- actions on one child -----------------------------------------------------


async def show_report(message: Message, api: ParentApi, child: ChildInfo) -> None:
    r = await api.report(child.id)
    await message.answer(texts.report_text(r), reply_markup=keyboards.report_kb(r))


async def show_progress(message: Message, api: ParentApi, child: ChildInfo) -> None:
    p = await api.progress(child.id)
    url = keyboards.cabinet_url(get_settings().public_url)
    kb = keyboards.cabinet_kb(url) if url else None
    await message.answer(texts.progress_text(p.child, p.topics), reply_markup=kb)


async def show_settings(message: Message, api: ParentApi, child: ChildInfo) -> None:
    await message.answer(texts.settings_text(child), reply_markup=keyboards.settings_kb(child))


async def show_code(message: Message, api: ParentApi, child: ChildInfo) -> None:
    code = await api.child_code(child.id)
    await message.answer(texts.code_text(child, code), reply_markup=keyboards.code_kb(child))


async def show_devices(message: Message, api: ParentApi, child: ChildInfo) -> None:
    devices = await api.devices(child.id)
    await message.answer(
        texts.devices_text(child, devices),
        reply_markup=keyboards.devices_kb(child, devices) if devices else None,
    )


async def show_reset(message: Message, api: ParentApi, child: ChildInfo) -> None:
    await message.answer(texts.reset_menu_text(child), reply_markup=keyboards.reset_kb(child))


ACTIONS: dict[str, ChildAction] = {
    "report": show_report,
    "progress": show_progress,
    "settings": show_settings,
    "code": show_code,
    "devices": show_devices,
    "reset": show_reset,
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


def wizard_step(me: ParentOut | None) -> Step | None:
    """Where the registration wizard stands, read from the API: None means it is over."""
    if me is None:
        return Step.PARENT
    if not me.children:
        return Step.CHILD
    return None


async def ask_parent_name(message: Message) -> None:
    user = message.from_user
    suggested = suggested_name(user.first_name, user.last_name) if user else None
    kb = keyboards.name_kb(suggested) if suggested else None
    await message.answer(texts.HELLO, reply_markup=kb)


@router.message(Command("start"))
async def cmd_start(message: Message, api: ParentApi) -> None:
    me = await api.me()
    step = wizard_step(me)
    if step is Step.PARENT:
        await ask_parent_name(message)
    elif step is Step.CHILD:
        await message.answer(texts.WELCOME_BACK)
    elif me is not None:
        await message.answer(texts.start_text(me.children))


@router.message(Command("help"))
async def cmd_help(message: Message, api: ParentApi) -> None:
    me = await api.me()
    if me is None:
        await ask_parent_name(message)
    else:
        await message.answer(texts.start_text(me.children))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, api: ParentApi) -> None:
    step = wizard_step(await api.me())
    if step is Step.PARENT:
        await message.answer(texts.CANCEL_UNREGISTERED)
    elif step is Step.CHILD:
        await message.answer(texts.CANCEL_NO_CHILDREN)
    else:
        await message.answer(texts.CANCELLED)


async def finish_with_child(message: Message, api: ParentApi, parent_name: str, text: str) -> None:
    """Step two: a login code joins an existing child, anything else names a new one."""
    code = normalize_code(text)
    if code is not None:
        try:
            child = await api.attach_child(code)
        except ApiError as exc:
            if exc.status != 404:
                raise
            await message.answer(texts.bad_code_text(code))
            return
        await message.answer(texts.registered_attached_text(parent_name, child))
        return
    child = await api.add_child(text)
    await message.answer(texts.registered_text(parent_name, child))
    login = await api.child_code(child.id)
    await message.answer(texts.code_text(child, login), reply_markup=keyboards.code_kb(child))


@router.message(Command("addchild"))
async def cmd_addchild(message: Message, command: CommandObject, api: ParentApi) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Напишите имя: /addchild Сандро")
        return
    code = normalize_code(name)
    if code is not None:  # an existing child's login code: attach, don't create
        try:
            child = await api.attach_child(code)
        except ApiError as exc:
            if exc.status != 404:
                raise
            await message.answer(texts.NO_SUCH_CODE)
            return
        await message.answer(texts.attached_text(child))
        return
    child = await api.add_child(name)
    await message.answer(f"Добавил: {escape(child.name)}. Код для входа: /code")


async def cmd_action(message: Message, api: ParentApi, command: CommandObject) -> None:
    await run_for_child(command.command, message, api)


router.message.register(cmd_action, Command(*ACTIONS))


@router.message()
async def wizard_answer(message: Message, api: ParentApi) -> None:
    """Anything that is not a known command: an answer to the wizard, or ignored."""
    me = await api.me()
    step = wizard_step(me)
    if step is None:
        return
    name, reply = check_name(message.text, step)
    if name is None:
        await message.answer(reply or texts.NEED_TEXT[step.value])
    elif step is Step.PARENT:
        registered = await api.register(name)
        await message.answer(texts.name_saved_text(registered.name or name))
    elif me is not None and me.name:
        await finish_with_child(message, api, me.name, name)


# --- callbacks ----------------------------------------------------------------


@router.callback_query(F.data == "reg:name")
async def cb_register_name(callback: CallbackQuery, api: ParentApi) -> None:
    """The «Я — Имя» button under the greeting: register with the Telegram profile name."""
    message = _message_of(callback)
    if await api.me() is not None:
        await callback.answer(texts.NAME_ALREADY_SAVED)
        if message is not None:
            await _edit(message, texts.HELLO, None)
        return
    name = suggested_name(callback.from_user.first_name, callback.from_user.last_name)
    if message is None or name is None:
        await callback.answer("Недоступно")
        return
    registered = await api.register(name)
    await callback.answer()
    await _edit(message, texts.HELLO, None)
    await message.answer(texts.name_saved_text(registered.name or name))


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


@router.callback_query(F.data.startswith("code:"))
async def cb_code(callback: CallbackQuery, api: ParentApi) -> None:
    _, action, child_id = (callback.data or "").split(":")
    message = _message_of(callback)
    child = await api.child(int(child_id))
    if message is None or child is None or action != "rotate":
        await callback.answer("Недоступно")
        return
    code = await api.rotate_code(child.id)
    await callback.answer("Цифры обновлены")
    await _edit(message, texts.code_text(child, code), keyboards.code_kb(child))


@router.callback_query(F.data.startswith("reset:"))
async def cb_reset(callback: CallbackQuery, api: ParentApi) -> None:
    """Two-step: a menu, then a confirmation; nothing is deleted before the "yes" button."""
    _, action, child_id = (callback.data or "").split(":")
    message = _message_of(callback)
    if message is None:
        await callback.answer("Недоступно")
        return
    if action == "cancel":
        await callback.answer()
        await _edit(message, texts.CANCELLED, None)
        return
    child = await api.child(int(child_id))
    if child is None:
        await callback.answer("Недоступно")
        return
    if action == "progress":
        await callback.answer()
        kb = keyboards.confirm_kb("Да, сбросить", f"reset:progress_yes:{child.id}")
        await _edit(message, texts.reset_progress_confirm_text(child), kb)
    elif action == "detach":
        await callback.answer()
        code = await api.child_code(child.id)
        kb = keyboards.confirm_kb("Да, отключить", f"reset:detach_yes:{child.id}")
        await _edit(message, texts.detach_confirm_text(child, code), kb)
    elif action == "progress_yes":
        await api.reset_progress(child.id)
        await callback.answer("Прогресс сброшен")
        await _edit(message, texts.reset_progress_done_text(child), None)
    elif action == "detach_yes":
        code = await api.child_code(child.id)  # shown in the farewell: the way back in
        await api.detach_child(child.id)
        await callback.answer("Ребёнок отключён")
        await _edit(message, texts.detach_done_text(child, code), None)
    else:
        await callback.answer("Недоступно")


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
