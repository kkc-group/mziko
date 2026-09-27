"""Calendar rules of the product. All business logic runs on Asia/Tbilisi time.

Nothing else in the codebase may call `datetime.now()`: callers receive `now`
as an argument so tests can pin the clock.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TBILISI = ZoneInfo("Asia/Tbilisi")


def now() -> datetime:
    """The only place that reads the system clock. Returns an aware UTC datetime."""
    return datetime.now(UTC)


def local_date(moment: datetime) -> date:
    """Calendar day in Tbilisi for an aware datetime."""
    if moment.tzinfo is None:
        raise ValueError("aware datetime required")
    return moment.astimezone(TBILISI).date()


def week_start(day: date) -> date:
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())
