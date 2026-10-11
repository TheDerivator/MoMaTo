"""Planned days into periods and weeks, project days and expected progress, with properties."""

from datetime import date
from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from momato.domain import planning as pl
from momato.domain.calendar import IsoWeek, Quarter
from momato.domain.capacity import WorkPattern

FULL = WorkPattern()
HALF_DAYS = st.integers(0, 140).map(lambda n: Fraction(n, 2))  # 0 to 70 days in 0.5 steps
PATTERNS = st.tuples(*[st.integers(0, 720)] * 5).filter(lambda m: sum(m) > 0)
Q4_26 = Quarter(2026, 4)


def test_a_whole_quarter_gets_all_its_planned_days() -> None:
    """[R4.3]"""
    planned = {Q4_26: Fraction(12)}
    assert pl.planned_in_period(planned, FULL, Q4_26.start, Q4_26.end) == 12


def test_a_period_gets_a_pro_rata_share_by_working_days() -> None:
    """[R4.3] October 2026 has 22 of the quarter's 66 workdays: a third."""
    planned = {Q4_26: Fraction(12)}
    assert pl.planned_in_period(planned, FULL, date(2026, 10, 1), date(2026, 10, 31)) == 4


def test_a_period_across_two_quarters_takes_from_both() -> None:
    """[R4.3] The last two weeks of Q3/26 and the first of Q4/26."""
    planned = {Quarter(2026, 3): Fraction(13), Q4_26: Fraction(66)}
    # 28 Sep to 9 Oct: Monday to Wednesday fall in Q3 (3 workdays), the rest in Q4 (7 workdays).
    got = pl.planned_in_period(planned, FULL, date(2026, 9, 28), date(2026, 10, 9))
    assert got == Fraction(13) * 3 / Quarter(2026, 3).workdays + Fraction(66) * 7 / 66


def test_the_persons_own_working_days_decide_the_share() -> None:
    """[R4.3] A four-day worker: Fridays carry no planned days."""
    four_days = WorkPattern((480, 480, 480, 480, 0))
    planned = {Q4_26: Fraction(8)}
    friday = pl.planned_in_period(planned, four_days, date(2026, 10, 9), date(2026, 10, 9))
    assert friday == 0
    week = pl.planned_days_in_week(planned, four_days, IsoWeek(2026, 41))
    assert week == Fraction(8) * 4 / four_days.working_days(Q4_26.start, Q4_26.end)


def test_nothing_is_planned_without_working_days_or_planned_days() -> None:
    assert pl.planned_in_period({}, FULL, date(2026, 10, 1), date(2026, 10, 31)) == 0
    weekend = pl.planned_in_period(
        {Q4_26: Fraction(5)}, FULL, date(2026, 10, 10), date(2026, 10, 11)
    )
    assert weekend == 0
    assert pl.planned_in_period({Q4_26: Fraction(0)}, FULL, Q4_26.start, Q4_26.end) == 0


def test_a_person_without_any_working_day_has_nothing_planned() -> None:
    """[R4.3] A work pattern of zeros (no hours at all) cannot carry planned days."""
    nobody = WorkPattern((0, 0, 0, 0, 0))
    assert pl.planned_in_period({Q4_26: Fraction(8)}, nobody, Q4_26.start, Q4_26.end) == 0


def test_weekly_planned_hours_are_planned_days_times_hours_per_day_and_stay_exact() -> None:
    """[R4.3] D-021"""
    planned = {Q4_26: Fraction(12)}
    hours = pl.weekly_planned_hours(planned, FULL, IsoWeek(2026, 41), 8)
    assert hours == Fraction(12) * 5 / 66 * 8  # 480/66 h, not rounded
    assert hours != 7  # shown whole elsewhere, never stored rounded


@given(PATTERNS, HALF_DAYS, st.integers(2024, 2030), st.integers(1, 4))
def test_the_weeks_of_a_quarter_add_up_to_its_planned_days_times_eight(
    minutes: tuple[int, int, int, int, int], days: Fraction, year: int, number: int
) -> None:
    """[R4.3] Weekly hours of all weeks overlapping a quarter sum to planned days × 8, exactly."""
    pattern = WorkPattern(minutes)
    quarter = Quarter(year, number)
    planned = {quarter: days}
    week = IsoWeek.of(quarter.start)
    total = Fraction(0)
    while week.monday <= quarter.end:
        total += pl.weekly_planned_hours(planned, pattern, week, 8)
        week = week.shifted(1)
    assert total == days * 8


def test_other_work_is_planned_at_a_share_of_the_weekly_target() -> None:
    """[R4.3] 10 % of 40 hours is 4 hours."""
    assert pl.other_work_planned_minutes(FULL, Fraction(1, 10)) == 240
    assert (
        pl.other_work_planned_minutes(WorkPattern((480, 480, 480, 480, 0)), Fraction(1, 10)) == 192
    )


def test_days_from_minutes() -> None:
    assert pl.days_from_minutes(480, 8) == 1
    assert pl.days_from_minutes(60, 8) == Fraction(1, 8)
    assert pl.days_from_minutes(450, 8) == Fraction(15, 16)


def test_a_past_quarter_is_expected_in_full_and_a_future_one_not_at_all() -> None:
    """[R4.4]"""
    planned = {
        Quarter(2026, 2): Fraction(10),
        Quarter(2026, 3): Fraction(20),
        Quarter(2027, 1): Fraction(7),
    }
    assert pl.expected_by_today(planned, date(2026, 10, 8)) == 30


def test_the_current_quarter_is_expected_by_the_workdays_up_to_today() -> None:
    """[R4.4] Q4/26 has 66 workdays; 1 to 8 October holds 6 (today included)."""
    planned = {Q4_26: Fraction(33)}
    assert pl.expected_by_today(planned, date(2026, 10, 8)) == Fraction(33) * 6 / 66
    assert pl.expected_by_today(planned, date(2026, 10, 1)) == Fraction(33) * 1 / 66
    assert pl.expected_by_today(planned, date(2026, 12, 31)) == 33  # the last day, a Thursday
    assert pl.expected_by_today(planned, date(2026, 9, 30)) == 0


def test_days_summary_has_planned_logged_expected_and_clamped_percentages() -> None:
    """[R4.4]"""
    planned = {Quarter(2026, 3): Fraction(20), Q4_26: Fraction(30)}
    summary = pl.days_summary(
        planned, logged_minutes=8 * 60 * 25, today=date(2026, 10, 8), hours_per_day=8
    )
    assert summary.planned == 50
    assert summary.logged == 25
    assert summary.expected == 20 + Fraction(30) * 6 / 66
    assert summary.logged_percent == 50
    assert summary.expected_percent == summary.expected * 2


def test_percentages_are_clamped_and_zero_without_planned_days() -> None:
    """[R4.4]"""
    over = pl.days_summary({Q4_26: Fraction(10)}, 8 * 60 * 30, date(2026, 10, 8), 8)
    assert over.logged == 30
    assert over.logged_percent == 100
    nothing = pl.days_summary({}, 8 * 60 * 3, date(2026, 10, 8), 8)
    assert (nothing.planned, nothing.logged_percent, nothing.expected_percent) == (0, 0, 0)
    assert nothing.logged == 3


@given(st.dictionaries(st.builds(Quarter, st.integers(2024, 2028), st.integers(1, 4)), HALF_DAYS))
def test_expected_never_exceeds_planned(planned: dict[Quarter, Fraction]) -> None:
    """[R4.4]"""
    summary = pl.days_summary(planned, 0, date(2026, 10, 8), 8)
    assert 0 <= summary.expected <= summary.planned
    assert 0 <= summary.expected_percent <= 100
