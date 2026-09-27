from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Child, Device, WeekStatus
from app.services.parents import CAP_OPTIONS, RATE_OPTIONS
from app.services.report import WeekReport
from bot.texts import week_label


def report_kb(r: WeekReport) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if r.week.status is WeekStatus.open:
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


def settings_kb(child: Child) -> InlineKeyboardMarkup:
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
                    callback_data=f"set:{child.id}:hint:toggle",
                )
            ],
        ]
    )


def children_kb(children: list[Child], action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c.name, callback_data=f"child:{action}:{c.id}")]
            for c in children
        ]
    )


def devices_kb(devices: list[Device]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Отключить: {d.name or 'устройство'} ({d.created_at:%d.%m})",
                    callback_data=f"dev:{d.id}",
                )
            ]
            for d in devices
        ]
    )
