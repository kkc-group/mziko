"""Study-day calendar grid for the parent card page.

Builds the 4-week Monday..Sunday grid ("Занятия за последние 4 недели" on
admin-parent-card.html) from the `study_days` list `GET /api/admin/parents/{id}`
returns. Kept out of format.py because it returns a small grid of dataclasses,
not a single formatted value.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.format import _format_week_range, _parse_date, _week_start

CALENDAR_WEEKS = 4
WEEKDAYS_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


@dataclass(frozen=True)
class CalendarCell:
    day: date
    # "done" (lesson finished), "part" (started, not finished), "future" (day
    # hasn't happened yet), or "" (day has already passed with no lesson).
    status: str
    is_today: bool


@dataclass(frozen=True)
class CalendarRow:
    label: str  # e.g. "28 сен – 4 окт"
    cells: list[CalendarCell]


@dataclass(frozen=True)
class CalendarGrid:
    rows: list[CalendarRow]  # newest week first, matching the weeks table below it
    sessions: int  # cells rendered "done" or "part" -- lessons visible in this grid


def calendar_grid(study_days: list[dict[str, Any]], today: date) -> CalendarGrid:
    """4 Monday-aligned weeks ending with the current one, newest first.

    `study_days` items carry "day" (an ISO date string) and "finished" (a
    bool), as the API returns them. The grid's window is Monday-aligned, so
    it can start a few days before or after the API's own rolling 28-day
    `study_days` window; entries outside the grid are simply not shown, same
    as the mockup's fixed 4-week calendar.
    """
    finished_by_day: dict[date, bool] = {}
    for entry in study_days:
        day = _parse_date(entry["day"])
        if day is not None:
            finished_by_day[day] = bool(entry["finished"])

    this_monday = _week_start(today)
    start_monday = this_monday - timedelta(weeks=CALENDAR_WEEKS - 1)

    rows: list[CalendarRow] = []
    sessions = 0
    for week_index in range(CALENDAR_WEEKS):
        monday = start_monday + timedelta(weeks=week_index)
        cells: list[CalendarCell] = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            if day > today:
                status = "future"
            elif day in finished_by_day:
                status = "done" if finished_by_day[day] else "part"
                sessions += 1
            else:
                status = ""
            cells.append(CalendarCell(day=day, status=status, is_today=day == today))
        label = _format_week_range(monday, monday + timedelta(days=6))
        rows.append(CalendarRow(label=label, cells=cells))
    rows.reverse()
    return CalendarGrid(rows=rows, sessions=sessions)
