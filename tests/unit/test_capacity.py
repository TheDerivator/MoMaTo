"""Work patterns, available time, availability, load and compare classes, with properties."""

from datetime import date
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from momato.domain import capacity as cap
from momato.domain.calendar import Quarter, weekdays_between
from tests.helpers import load_fixture

PATTERNS = st.tuples(*[st.integers(0, 720)] * 5).filter(lambda m: sum(m) > 0)


def test_the_default_pattern_is_eight_hours_a_day() -> None:
    """[R4.2]"""
    pattern = cap.WorkPattern()
    assert pattern.weekly_target_minutes == 2400
    assert pattern.capacity_factor == 1
    assert pattern.target_minutes(date(2026, 10, 8)) == 480  # Thursday
    assert pattern.target_minutes(date(2026, 10, 10)) == 0  # Saturday
    assert pattern.is_working_day(date(2026, 10, 9))
    assert not pattern.is_working_day(date(2026, 10, 11))


def test_a_four_day_pattern_has_a_capacity_factor_of_four_fifths() -> None:
    """[R4.2] Eva Janssens works four days."""
    pattern = cap.WorkPattern((480, 480, 480, 480, 0))
    assert pattern.weekly_target_minutes == 1920
    assert pattern.capacity_factor == Fraction(4, 5)
    assert not pattern.is_working_day(date(2026, 10, 9))  # Friday
    assert pattern.working_days(date(2026, 10, 5), date(2026, 10, 11)) == 4


def test_a_pattern_needs_five_non_negative_numbers() -> None:
    with pytest.raises(ValueError, match="five non-negative"):
        cap.WorkPattern((480, 480, 480, 480))  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="five non-negative"):
        cap.WorkPattern((480, 480, 480, 480, -1))


def test_available_time_is_the_targets_minus_time_off() -> None:
    """[R4.2]"""
    week = (date(2026, 10, 5), date(2026, 10, 11))
    assert cap.available_minutes(cap.WorkPattern(), *week, time_off_minutes=0) == 2400
    assert cap.available_minutes(cap.WorkPattern(), *week, time_off_minutes=480) == 1920
    assert cap.available_minutes(cap.WorkPattern(), *week, time_off_minutes=99_999) == 0


@given(PATTERNS, st.dates(date(2020, 1, 1), date(2030, 1, 1)), st.integers(0, 60))
def test_target_minutes_between_matches_a_day_by_day_sum(
    minutes: tuple[int, int, int, int, int], start: date, length: int
) -> None:
    pattern = cap.WorkPattern(minutes)
    end = date.fromordinal(start.toordinal() + length)
    days = [date.fromordinal(start.toordinal() + i) for i in range(length + 1)]
    assert pattern.target_minutes_between(start, end) == sum(
        pattern.target_minutes(d) for d in days
    )
    assert pattern.working_days(start, end) == sum(1 for d in days if pattern.is_working_day(d))


def test_availability_defaults_to_220_days_times_the_capacity_factor() -> None:
    """[R4.3]"""
    assert cap.year_availability_days(None, cap.WorkPattern(), 220) == 220
    four_days = cap.WorkPattern((480, 480, 480, 480, 0))
    assert cap.year_availability_days(None, four_days, 220) == 176
    assert cap.year_availability_days(Fraction(200), four_days, 220) == 200  # an override wins
    assert cap.year_availability_days(Fraction(0), four_days, 220) == 0


@given(st.integers(2000, 2100), st.fractions(0, 400))
def test_a_years_quarter_availabilities_add_up_to_the_year(year: int, days: Fraction) -> None:
    """[R4.3]"""
    total = sum(
        (cap.quarter_availability_days(days, Quarter(year, n)) for n in range(1, 5)), Fraction(0)
    )
    assert total == days


def test_a_period_takes_its_share_of_the_year_by_workdays() -> None:
    year = Fraction(220)
    q4 = Quarter(2026, 4)
    assert cap.period_availability_days(year, q4.start, q4.end) == cap.quarter_availability_days(
        year, q4
    )
    one_week = cap.period_availability_days(year, date(2026, 10, 5), date(2026, 10, 9))
    assert one_week == year * 5 / weekdays_between(date(2026, 1, 1), date(2026, 12, 31))


LOADS = load_fixture("load_classes")["cases"]
COMPARES = load_fixture("compare_classes")["cases"]


@pytest.mark.parametrize("case", LOADS, ids=lambda c: f"{c['value']}/{c['capacity']}")
def test_load_classes_follow_the_hand_derived_boundaries(case: dict[str, int | str]) -> None:
    """[R4.5]"""
    assert cap.load_class(Fraction(case["value"]), Fraction(case["capacity"])) == case["class"]


@pytest.mark.parametrize("case", COMPARES, ids=lambda c: f"{c['spent']}/{c['planned']}")
def test_compare_classes_follow_the_hand_derived_boundaries(case: dict[str, int | str]) -> None:
    """[R4.5]"""
    assert cap.compare_class(Fraction(case["spent"]), Fraction(case["planned"])) == case["class"]


LOAD_ORDER = [
    cap.LoadClass.EMPTY,
    cap.LoadClass.LIGHT,
    cap.LoadClass.COMFORTABLE,
    cap.LoadClass.NEARLY_FULL,
    cap.LoadClass.OVER,
]


@given(st.integers(1, 5000), st.integers(0, 5000), st.integers(0, 5000))
def test_load_classes_never_decrease_as_the_value_grows(capacity: int, a: int, b: int) -> None:
    """[R4.5]"""
    low, high = sorted((a, b))
    order_low = LOAD_ORDER.index(cap.load_class(low, capacity))
    order_high = LOAD_ORDER.index(cap.load_class(high, capacity))
    assert order_low <= order_high


def test_every_class_has_a_label() -> None:
    assert set(cap.LOAD_LABELS) == set(cap.LoadClass)
    assert set(cap.COMPARE_LABELS) == set(cap.CompareClass)
    assert cap.LOAD_LABELS[cap.LoadClass.NEARLY_FULL] == "Nearly full"
    assert cap.LOAD_LABELS[cap.LoadClass.OVER] == "Over capacity"
    assert cap.COMPARE_LABELS[cap.CompareClass.ON_TRACK] == "On track"
