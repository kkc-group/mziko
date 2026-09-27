"""Message texts. HTML parse mode; every user-provided string goes through esc()."""

from decimal import Decimal
from html import escape as esc

from app.schemas.parent import (
    ChildInfo,
    DeviceOut,
    TopicProgressOut,
    WeekBrief,
    WeekReportOut,
    WordBrief,
)

DOTS = {0: "○○○", 1: "●○○", 2: "●●○", 3: "●●●"}


def lari(value: Decimal | float | int) -> str:
    return f"{Decimal(str(value)):.1f}".replace(".", ",") + " ₾"


def week_label(week: WeekBrief) -> str:
    return f"{week.week_start:%d.%m}–{week.week_end:%d.%m}"


def start_text(children: list[ChildInfo]) -> str:
    names = ", ".join(esc(c.name) for c in children) or "пока никого"
    return (
        "Привет! Я Мзико, бот для родителей.\n"
        f"Дети: {names}\n\n"
        "/report — итоги недели\n"
        "/progress — прогресс по словам\n"
        "/settings — курс, лимит, подсказка\n"
        "/pair — привязать iPad ребёнка\n"
        "/devices — привязанные устройства\n"
        "/addchild Имя — добавить ребёнка"
    )


def report_text(r: WeekReportOut) -> str:
    learned = f"Выучено слов: {len(r.learned)}"
    if r.learned:
        learned += " (" + " ".join(esc(w.icon) for w in r.learned) + ")"
    lines = [
        f"<b>Неделя {week_label(r.week)}: итоги {esc(r.child.name)}</b>",
        f"Занимался {r.days_studied} из 7 дней",
        learned,
        f"Монет: {r.week.coins} → <b>{lari(r.week.lari_due)}</b>"
        + (" (достигнут лимит)" if r.cap_reached else ""),
    ]
    if r.week.status == "paid":
        lines.append(f"✅ Выплачено {lari(r.week.lari_paid or 0)}")
    else:
        lines.append("Выдайте наличные и нажмите «Выплачено».")
    if r.unpaid_past:
        lines.append("")
        lines.append("К выплате за прошлые недели:")
        for w in r.unpaid_past:
            lines.append(f"• {week_label(w)} — {lari(w.lari_due)} ({w.coins} монет)")
    return "\n".join(lines)


def words_of_week_text(child: ChildInfo, words: list[WordBrief]) -> str:
    if not words:
        return f"На этой неделе {esc(child.name)} пока не довёл до конца ни одного слова."
    rows = [f"{esc(w.icon)} <b>{esc(w.ka)}</b> — {esc(w.tr)} · {esc(w.ru)}" for w in words]
    return "Слова недели:\n" + "\n".join(rows)


def progress_text(child: ChildInfo, topics: list[TopicProgressOut]) -> str:
    blocks = [f"<b>Прогресс {esc(child.name)}</b>"]
    for tp in topics:
        blocks.append("")
        blocks.append(f"{tp.icon} <b>{esc(tp.title_ru)}</b> — {tp.learned} из {tp.total}")
        for word in tp.words:
            blocks.append(f"{DOTS[word.stage]} {esc(word.ka)} · {esc(word.ru)}")
    return "\n".join(blocks)


def settings_text(child: ChildInfo) -> str:
    return (
        f"<b>Настройки {esc(child.name)}</b>\n"
        f"Курс: {child.rate} монет = 1 ₾\n"
        f"Лимит: до {child.cap_lari} ₾ в неделю\n"
        f"Подсказка кириллицей: {'вкл' if child.show_hint else 'выкл'}"
    )


def pair_text(child: ChildInfo, url: str) -> str:
    return (
        f"Откройте эту ссылку на устройстве {esc(child.name)} в течение 15 минут:\n{esc(url)}\n\n"
        "Потом добавьте страницу на экран «Домой»."
    )


def devices_text(child: ChildInfo, devices: list[DeviceOut]) -> str:
    if not devices:
        return f"У {esc(child.name)} нет привязанных устройств. Привязать: /pair"
    rows = [
        f"• {esc(d.name or 'устройство')} — с {d.created_at:%d.%m.%Y}"
        + (f", был {d.last_seen_at:%d.%m %H:%M}" if d.last_seen_at else "")
        for d in devices
    ]
    return f"Устройства {esc(child.name)}:\n" + "\n".join(rows)
