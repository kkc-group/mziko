"""Unit tests for the 4-week study calendar grid behind the parent card page."""

from datetime import date

from app.calendar import calendar_grid

TODAY = date(2026, 10, 1)  # Thursday, matching format.py's reference date
THIS_MONDAY = date(2026, 9, 28)
WINDOW_START = date(2026, 9, 7)  # Monday, 3 full weeks before THIS_MONDAY


def test_today_with_no_lesson_is_marked_today_but_has_no_lesson_status() -> None:
    grid = calendar_grid([], TODAY)
    today_cell = next(c for row in grid.rows for c in row.cells if c.day == TODAY)
    assert today_cell.is_today
    assert today_cell.status == ""


def test_finished_day_is_done() -> None:
    grid = calendar_grid([{"day": "2026-09-29", "finished": True}], TODAY)
    cell = next(c for row in grid.rows for c in row.cells if c.day == date(2026, 9, 29))
    assert cell.status == "done"
    assert grid.sessions == 1


def test_unfinished_day_is_part() -> None:
    grid = calendar_grid([{"day": "2026-09-29", "finished": False}], TODAY)
    cell = next(c for row in grid.rows for c in row.cells if c.day == date(2026, 9, 29))
    assert cell.status == "part"
    assert grid.sessions == 1


def test_day_after_today_is_future() -> None:
    grid = calendar_grid([], TODAY)
    tomorrow = next(c for row in grid.rows for c in row.cells if c.day == date(2026, 10, 2))
    assert tomorrow.status == "future"


def test_grid_starts_on_the_monday_four_weeks_back() -> None:
    grid = calendar_grid([{"day": WINDOW_START.isoformat(), "finished": True}], TODAY)
    oldest_row = grid.rows[-1]
    assert oldest_row.cells[0].day == WINDOW_START
    assert oldest_row.cells[0].status == "done"


def test_day_before_the_window_is_dropped() -> None:
    before_window = date(2026, 9, 6)
    grid = calendar_grid([{"day": before_window.isoformat(), "finished": True}], TODAY)
    assert grid.sessions == 0
    assert all(c.day != before_window for row in grid.rows for c in row.cells)


def test_rows_are_newest_week_first_with_seven_days_each() -> None:
    grid = calendar_grid([], TODAY)
    assert len(grid.rows) == 4
    assert all(len(row.cells) == 7 for row in grid.rows)
    assert grid.rows[0].label == "28 сен – 4 окт"
    assert grid.rows[-1].label == "7–13 сен"
    assert grid.rows[0].cells[0].day == THIS_MONDAY
