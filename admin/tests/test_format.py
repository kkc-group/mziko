"""Unit tests for the pure formatting helpers behind the parents page."""

from datetime import date

from app.format import (
    activity_class,
    children_count,
    is_current_week,
    last_week_label,
    parents_count,
    registered_date,
    relative_date,
    short_date,
    this_week_label,
    words_count,
)

TODAY = date(2026, 10, 1)  # Thursday, matching the mockup's reference date


def test_relative_date_today() -> None:
    assert relative_date(date(2026, 10, 1), TODAY) == "сегодня"


def test_relative_date_yesterday() -> None:
    assert relative_date(date(2026, 9, 30), TODAY) == "вчера"


def test_relative_date_two_days_ago() -> None:
    assert relative_date(date(2026, 9, 29), TODAY) == "2 дн. назад"


def test_relative_date_thirteen_days_ago_is_still_relative() -> None:
    assert relative_date(date(2026, 9, 18), TODAY) == "13 дн. назад"


def test_relative_date_fourteen_days_ago_falls_back_to_a_date() -> None:
    assert relative_date(date(2026, 9, 17), TODAY) == "17 сен"


def test_relative_date_none_means_never_studied() -> None:
    assert relative_date(None, TODAY) == "не занимался"


def test_relative_date_accepts_iso_strings() -> None:
    assert relative_date("2026-10-01", TODAY) == "сегодня"


def test_activity_class_boundaries() -> None:
    assert activity_class(date(2026, 10, 1), TODAY) == "today"
    assert activity_class(date(2026, 9, 30), TODAY) == ""
    assert activity_class(date(2026, 9, 18), TODAY) == ""
    assert activity_class(date(2026, 9, 17), TODAY) == "old"
    assert activity_class(None, TODAY) == "old"


def test_words_count_declensions() -> None:
    assert words_count(1) == "1 слово"
    assert words_count(2) == "2 слова"
    assert words_count(5) == "5 слов"
    assert words_count(11) == "11 слов"
    assert words_count(21) == "21 слово"


def test_parents_count_declensions() -> None:
    assert parents_count(1) == "1 родитель"
    assert parents_count(2) == "2 родителя"
    assert parents_count(5) == "5 родителей"
    assert parents_count(11) == "11 родителей"
    assert parents_count(21) == "21 родитель"


def test_children_count_declensions() -> None:
    assert children_count(1) == "1 ребёнок"
    assert children_count(2) == "2 ребёнка"
    assert children_count(5) == "5 детей"
    assert children_count(11) == "11 детей"
    assert children_count(21) == "21 ребёнок"


def test_registered_date_formats_as_ddmmyyyy() -> None:
    assert registered_date("2026-08-12T10:23:00") == "12.08.2026"


def test_week_labels_within_the_same_month() -> None:
    # Thu 1 Oct 2026: this week is Mon 28 Sep - Sun 4 Oct (crosses months),
    # last week is Mon 21 Sep - Sun 27 Sep (stays within September).
    assert this_week_label(TODAY) == "28 сен – 4 окт"
    assert last_week_label(TODAY) == "21–27 сен"


def test_short_date_formats_day_and_month() -> None:
    assert short_date("2026-09-28") == "28 сен"
    assert short_date(None) == "—"


def test_is_current_week_matches_this_mondays_week_start() -> None:
    assert is_current_week("2026-09-28", TODAY) is True  # this week's Monday
    assert is_current_week("2026-09-21", TODAY) is False  # last week's Monday
    assert is_current_week(None, TODAY) is False
