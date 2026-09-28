"""Server-side formatting for the parents page: relative dates, money, Russian plurals.

Pure functions, registered as Jinja filters in `app.main` so templates call
them directly (`{{ value | relative_date }}`). Kept dependency-free from the
backend package; the Tbilisi calendar rule is copied from
`backend/app/core/clock.py` rather than imported (the admin app must not
import the backend).
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TBILISI = ZoneInfo("Asia/Tbilisi")

MONTHS_RU = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)

DateLike = date | datetime | str | None


def today_tbilisi() -> date:
    """Calendar day in Tbilisi, right now."""
    return datetime.now(UTC).astimezone(TBILISI).date()


def _parse_date(value: DateLike) -> date | None:
    """Accept a date, a datetime, an ISO string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(TBILISI).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural form for a count: 1 -> one, 2-4 -> few, else -> many (with the 11-14 trap)."""
    a, b = n % 10, n % 100
    if a == 1 and b != 11:
        return one
    if 2 <= a <= 4 and not (12 <= b <= 14):
        return few
    return many


def words_count(n: int) -> str:
    return f"{n} {_plural(n, 'слово', 'слова', 'слов')}"


def parents_count(n: int) -> str:
    return f"{n} {_plural(n, 'родитель', 'родителя', 'родителей')}"


def children_count(n: int) -> str:
    return f"{n} {_plural(n, 'ребёнок', 'ребёнка', 'детей')}"


def relative_date(value: DateLike, today: date | None = None) -> str:
    """ "сегодня" / "вчера" / "N дн. назад" (up to 13 days) / "8 сен"; None means "не занимался"."""
    day = _parse_date(value)
    if day is None:
        return "не занимался"
    ref = today or today_tbilisi()
    delta = (ref - day).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "вчера"
    if delta <= 13:
        return f"{delta} дн. назад"
    return f"{day.day} {MONTHS_RU[day.month - 1]}"


def activity_class(value: DateLike, today: date | None = None) -> str:
    """CSS class for the relative-date span: "today" / "old" (>13 days or never) / "" (recent)."""
    day = _parse_date(value)
    if day is None:
        return "old"
    ref = today or today_tbilisi()
    delta = (ref - day).days
    if delta == 0:
        return "today"
    if delta > 13:
        return "old"
    return ""


def registered_date(value: DateLike) -> str:
    """dd.mm.yyyy, as in the "Регистрация" column."""
    day = _parse_date(value)
    if day is None:
        return "—"
    return day.strftime("%d.%m.%Y")


def short_date(value: DateLike) -> str:
    """ "28 сен" -- a single day, not a range (weeks table row label, "paid on" date)."""
    day = _parse_date(value)
    if day is None:
        return "—"
    return f"{day.day} {MONTHS_RU[day.month - 1]}"


def lari(amount: float) -> str:
    """1234.5 -> "1234,5 ₾" (comma decimal separator, as used across the product)."""
    return f"{amount:.1f}".replace(".", ",") + " ₾"


def _week_start(day: date) -> date:
    """Monday of the week containing `day` (same rule as backend/app/core/clock.py)."""
    return day - timedelta(days=day.weekday())


def _format_week_range(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_RU[start.month - 1]}"
    return f"{start.day} {MONTHS_RU[start.month - 1]} – {end.day} {MONTHS_RU[end.month - 1]}"


def this_week_label(today: date) -> str:
    """The current week's range, e.g. "28 сен – 4 окт", for the table header subtext."""
    start = _week_start(today)
    return _format_week_range(start, start + timedelta(days=6))


def last_week_label(today: date) -> str:
    """The previous week's range, e.g. "21–27 сен", for the table header subtext."""
    start = _week_start(today) - timedelta(days=7)
    return _format_week_range(start, start + timedelta(days=6))


def is_current_week(week_start_value: DateLike, today: date) -> bool:
    """True when `week_start_value` (a week row's Monday) is the Monday of today's week.

    Position in the `weeks` list (newest first) is not a reliable signal: a
    child who hasn't played yet this week has no row for it, so the newest
    row can be an older, already-closed week. Comparing the actual Monday is
    what the parent-card mockup's "открыта" chip means.
    """
    day = _parse_date(week_start_value)
    return day is not None and day == _week_start(today)
