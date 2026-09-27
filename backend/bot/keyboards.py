from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.schemas.parent import CAP_OPTIONS, RATE_OPTIONS, ChildInfo, DeviceOut, WeekReportOut
from bot.texts import week_label


def report_kb(r: WeekReportOut) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if r.week.status == "open":
        rows.append(
            [
                InlineKeyboardButton(text="Выплачено", callback_data=f"pay:{r.week.id}"),
                InlineKeyboardButton(text="Слова недели", callback_data=f"words:{r.week.id}"),
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text="Слова недели", callback_data=f"words:{r.week.id}")])
    for w in r.unpaid_past:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Выплачено за {week_label(w)}", callback_data=f"pay:{w.id}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_kb(child: ChildInfo) -> InlineKeyboardMarkup:
    def mark(value: int, current: int) -> str:
        return f"✓ {value}" if value == current else str(value)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Курс, монет за 1 ₾:", callback_data="noop")],
            [
                InlineKeyboardButton(
                    text=mark(v, child.rate), callback_data=f"set:{child.id}:rate:{v}"
                )
                for v in RATE_OPTIONS
            ],
            [InlineKeyboardButton(text="Лимит в неделю, ₾:", callback_data="noop")],
            [
                InlineKeyboardButton(
                    text=mark(v, child.cap_lari), callback_data=f"set:{child.id}:cap:{v}"
                )
                for v in CAP_OPTIONS
            ],
            [
                InlineKeyboardButton(
                    text=f"Подсказка кириллицей: {'вкл ✓' if child.show_hint else 'выкл'}",
                    # The button carries the value to set, so no read is needed to toggle.
                    callback_data=f"set:{child.id}:hint:{0 if child.show_hint else 1}",
                )
            ],
        ]
    )


def code_kb(child: ChildInfo) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новые цифры", callback_data=f"code:rotate:{child.id}")]
        ]
    )


def reset_kb(child: ChildInfo) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сбросить прогресс", callback_data=f"reset:progress:{child.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отключить ребёнка", callback_data=f"reset:detach:{child.id}"
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="reset:cancel:0")],
        ]
    )


def confirm_kb(yes_text: str, yes_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_text, callback_data=yes_data),
                InlineKeyboardButton(text="Отмена", callback_data="reset:cancel:0"),
            ]
        ]
    )


def children_kb(children: list[ChildInfo], action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.name, callback_data=f"child:{action}:{c.id}")]
            for c in children
        ]
    )


def devices_kb(child: ChildInfo, devices: list[DeviceOut]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Отключить: {d.name or 'устройство'} ({d.created_at:%d.%m})",
                    callback_data=f"dev:{child.id}:{d.id}",
                )
            ]
            for d in devices
        ]
    )
