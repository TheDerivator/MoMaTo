"""Planned days into periods and weeks, project days and expected progress (R4.3, R4.4).

Planned days are set per (project, person, quarter). A period's share of a quarter is pro rata over
the person's working days; everything is an exact `Fraction`, so the weeks of a quarter add up to
exactly the quarter's days (D-021).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from momato.domain.calendar import IsoWeek, Quarter, quarters_overlapping, weekdays_between
from momato.domain.capacity import MINUTES_PER_HOUR, WorkPattern

HUNDRED = Fraction(100)


def planned_in_period(
    planned: Mapping[Quarter, Fraction], pattern: WorkPattern, start: date, end: date
) -> Fraction:
    """Σ over quarters q overlapping the period of planned(q) × wd(period ∩ q) / wd(q)."""
    total = Fraction(0)
    for quarter in quarters_overlapping(start, end):
        days = planned.get(quarter, Fraction(0))
        if days == 0:
            continue
        in_quarter = pattern.working_days(quarter.start, quarter.end)
        if in_quarter == 0:
            continue
        overlap = pattern.working_days(max(start, quarter.start), min(end, quarter.end))
        total += days * overlap / in_quarter
    return total


def planned_days_in_week(
    planned: Mapping[Quarter, Fraction], pattern: WorkPattern, week: IsoWeek
) -> Fraction:
    return planned_in_period(planned, pattern, week.monday, week.sunday)


def weekly_planned_hours(
    planned: Mapping[Quarter, Fraction],
    pattern: WorkPattern,
    week: IsoWeek,
    hours_per_day: int,
) -> Fraction:
    """A project line's planned hours in a week: planned days in the week × hours per day, exact."""
    return planned_days_in_week(planned, pattern, week) * hours_per_day


def other_work_planned_minutes(pattern: WorkPattern, share: Fraction) -> Fraction:
    """Other work is planned at a share of the weekly target (default 10 %: 4 h of 40)."""
    return pattern.weekly_target_minutes * share


def days_from_minutes(minutes: int | Fraction, hours_per_day: int) -> Fraction:
    return Fraction(minutes) / (hours_per_day * MINUTES_PER_HOUR)


@dataclass(frozen=True)
class DaysSummary:
    planned: Fraction
    logged: Fraction
    expected: Fraction
    logged_percent: Fraction  # of planned, clamped to 0..100
    expected_percent: Fraction


def _percent(part: Fraction, whole: Fraction) -> Fraction:
    if whole <= 0:
        return Fraction(0)
    return min(HUNDRED, max(Fraction(0), part * HUNDRED / whole))


def expected_by_today(planned: Mapping[Quarter, Fraction], today: date) -> Fraction:
    """Σ over quarters of planned(q) × (workdays of q up to today / workdays(q))."""
    total = Fraction(0)
    for quarter, days in planned.items():
        if days == 0 or quarter.start > today:
            continue
        if quarter.end <= today:
            total += days
        else:
            total += days * weekdays_between(quarter.start, today) / quarter.workdays
    return total


def days_summary(
    planned: Mapping[Quarter, Fraction], logged_minutes: int, today: date, hours_per_day: int
) -> DaysSummary:
    """Planned, logged and expected days of a project, a person on it, an action plan."""
    planned_total = sum(planned.values(), Fraction(0))
    logged = days_from_minutes(logged_minutes, hours_per_day)
    expected = expected_by_today(planned, today)
    return DaysSummary(
        planned=planned_total,
        logged=logged,
        expected=expected,
        logged_percent=_percent(logged, planned_total),
        expected_percent=_percent(expected, planned_total),
    )
