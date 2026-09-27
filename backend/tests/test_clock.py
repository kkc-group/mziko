from datetime import UTC, date, datetime

import pytest

from app.core.clock import local_date, week_start


def test_local_date_uses_tbilisi_calendar() -> None:
    # 22:30 UTC on Sunday is already 02:30 Monday in Tbilisi (UTC+4).
    assert local_date(datetime(2026, 9, 27, 22, 30, tzinfo=UTC)) == date(2026, 9, 28)
    assert local_date(datetime(2026, 9, 27, 19, 59, tzinfo=UTC)) == date(2026, 9, 27)


def test_local_date_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        local_date(datetime(2026, 9, 27, 12, 0))


def test_week_start_is_monday() -> None:
    assert week_start(date(2026, 9, 27)) == date(2026, 9, 21)  # Sunday -> its Monday
    assert week_start(date(2026, 9, 28)) == date(2026, 9, 28)  # Monday -> itself
    assert week_start(date(2026, 10, 1)) == date(2026, 9, 28)  # Thursday
