"""ISO weeks, quarters, workdays, spent buckets and timeline windows, with properties. [R4.1]"""

from datetime import date, timedelta
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from momato.domain import calendar as cal
from tests.helpers import load_fixture

BUCKETS = load_fixture("buckets")
DATES = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


def _iso(value: str) -> date:
    return date.fromisoformat(value)


def _brute_weekdays(start: date, end: date) -> int:
    days = (start + timedelta(days=i) for i in range((end - start).days + 1))
    return sum(1 for d in days if d.weekday() < 5)


# ---------------------------------------------------------------- weeks and workdays


def test_the_design_date_is_a_thursday_in_week_41() -> None:
    today = date(2026, 10, 8)
    assert today.weekday() == 3
    week = cal.IsoWeek.of(today)
    assert (week.year, week.week, week.label) == (2026, 41, "2026-W41")
    assert week.monday == date(2026, 10, 5)
    assert week.friday == date(2026, 10, 9)
    assert week.sunday == date(2026, 10, 11)
    assert week.days[0] == date(2026, 10, 5)
    assert week.days[4] == date(2026, 10, 9)


def test_week_53_exists_in_2026_and_the_iso_year_differs_from_the_calendar_year() -> None:
    assert cal.IsoWeek.parse("2026-W53").monday == date(2026, 12, 28)
    assert cal.IsoWeek.of(date(2027, 1, 1)) == cal.IsoWeek(2026, 53)
    assert cal.IsoWeek.of(date(2024, 12, 30)) == cal.IsoWeek(2025, 1)


@pytest.mark.parametrize("label", ["2026-W54", "2027-W53", "2026-W00", "2026-41", "26-W41", ""])
def test_impossible_week_labels_are_refused(label: str) -> None:
    with pytest.raises(ValueError, match=r"ISO week|out of range|Invalid"):
        cal.IsoWeek.parse(label)


def test_shifting_weeks_crosses_years() -> None:
    assert cal.IsoWeek(2026, 41).shifted(-1) == cal.IsoWeek(2026, 40)
    assert cal.IsoWeek(2026, 53).shifted(1) == cal.IsoWeek(2027, 1)
    assert cal.IsoWeek(2027, 1).shifted(-1) == cal.IsoWeek(2026, 53)


@given(DATES)
def test_iso_week_labels_round_trip_and_contain_the_date(d: date) -> None:
    week = cal.IsoWeek.of(d)
    assert cal.IsoWeek.parse(week.label) == week
    assert week.monday <= d <= week.sunday
    assert week.monday.weekday() == 0


@given(DATES, DATES)
def test_weekday_counts_match_a_day_by_day_count(a: date, b: date) -> None:
    start, end = min(a, b), min(max(a, b), min(a, b) + timedelta(days=800))
    assert cal.weekdays_between(start, end) == _brute_weekdays(start, end)
    for weekday in range(7):
        expected = sum(
            1
            for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() == weekday
        )
        assert cal.count_weekday(weekday, start, end) == expected


def test_an_empty_range_has_no_days() -> None:
    assert cal.weekdays_between(date(2026, 10, 9), date(2026, 10, 8)) == 0
    assert cal.count_weekday(0, date(2026, 10, 9), date(2026, 10, 8)) == 0
    assert cal.count_weekday(0, date(2026, 10, 8), date(2026, 10, 8)) == 0  # a Thursday


def test_is_weekday() -> None:
    assert cal.is_weekday(date(2026, 10, 9))
    assert not cal.is_weekday(date(2026, 10, 10))


# ---------------------------------------------------------------- quarters


def test_quarters() -> None:
    q = cal.Quarter.containing(date(2026, 10, 8))
    assert (q.year, q.number, q.label) == (2026, 4, "Q4/26")
    assert (q.start, q.end) == (date(2026, 10, 1), date(2026, 12, 31))
    assert q.workdays == 66
    assert q.shifted(1) == cal.Quarter(2027, 1)
    assert q.shifted(-4) == cal.Quarter(2025, 4)
    assert cal.Quarter(2028, 1).end == date(2028, 3, 31)
    assert cal.Quarter(2024, 1).start == date(2024, 1, 1)
    assert cal.Quarter.starting(date(2026, 4, 1)) == cal.Quarter(2026, 2)
    with pytest.raises(ValueError, match="first day"):
        cal.Quarter.starting(date(2026, 4, 2))


@given(DATES)
def test_a_date_lies_in_its_quarter(d: date) -> None:
    q = cal.Quarter.containing(d)
    assert q.start <= d <= q.end
    assert cal.Quarter.containing(q.end + timedelta(days=1)) == q.shifted(1)


def test_quarters_overlapping_a_range() -> None:
    result = cal.quarters_overlapping(date(2026, 2, 10), date(2027, 1, 1))
    assert [q.label for q in result] == ["Q1/26", "Q2/26", "Q3/26", "Q4/26", "Q1/27"]
    assert cal.quarters_overlapping(date(2026, 5, 1), date(2026, 5, 1)) == [cal.Quarter(2026, 2)]
    assert cal.quarters_overlapping(date(2026, 5, 2), date(2026, 5, 1)) == []


@given(st.integers(2000, 2100))
def test_the_workdays_of_a_years_quarters_add_up_to_the_year(year: int) -> None:
    assert sum(cal.Quarter(year, n).workdays for n in range(1, 5)) == cal.year_workdays(year)


# ---------------------------------------------------------------- buckets and windows


@pytest.mark.parametrize("case", BUCKETS["spent"], ids=lambda c: c["name"])
def test_spent_buckets_match_the_hand_derived_table(case: dict[str, object]) -> None:
    """[R4.11]"""
    result = cal.spent_buckets(cal.Period(str(case["period"])), _iso(str(case["today"])))
    assert result.range_label == case["range"]
    assert result.unit == case["unit"]
    assert [(b.key, b.sub, b.start.isoformat(), b.end.isoformat()) for b in result.buckets] == [
        tuple(row)
        for row in case["buckets"]  # pyright: ignore[reportGeneralTypeIssues]
    ]


@pytest.mark.parametrize("case", BUCKETS["planned"], ids=lambda c: c["name"])
def test_planned_buckets_are_eight_quarters(case: dict[str, object]) -> None:
    """[R4.1]"""
    result = cal.planned_buckets(_iso(str(case["today"])))
    assert result.range_label == case["range"]
    assert result.unit == case["unit"]
    assert [(b.key, b.sub, b.start.isoformat(), b.end.isoformat()) for b in result.buckets] == [
        tuple(row)
        for row in case["buckets"]  # pyright: ignore[reportGeneralTypeIssues]
    ]


def test_the_current_quarter_is_the_one_containing_today() -> None:
    assert cal.current_quarter(date(2026, 10, 8)).label == "Q4/26"


@pytest.mark.parametrize("case", BUCKETS["windows"], ids=lambda c: c["today"])
def test_timeline_windows(case: dict[str, str]) -> None:
    """[R4.12]"""
    assert cal.timeline_window(_iso(case["today"])) == (_iso(case["start"]), _iso(case["end"]))


@given(DATES, st.sampled_from(list(cal.Period)))
def test_spent_buckets_partition_the_working_days_and_end_before_today(
    today: date, period: cal.Period
) -> None:
    """[R4.11] Buckets are ordered, never overlap, leave no working day out, and are all past."""
    buckets = cal.spent_buckets(period, today).buckets
    for earlier, later in pairwise(buckets):
        assert earlier.end < later.start
        if period is cal.Period.YEAR:  # months are contiguous
            assert earlier.end + timedelta(days=1) == later.start
    first, last = buckets[0], buckets[-1]
    covered = sum(cal.weekdays_between(b.start, b.end) for b in buckets)
    assert covered == cal.weekdays_between(first.start, last.end)
    assert last.end < today
    if period is cal.Period.YEAR:  # the month before this one
        assert last.end + timedelta(days=1) == today.replace(day=1)
    else:  # the week before this one
        assert last.end == cal.IsoWeek.of(today).shifted(-1).friday
