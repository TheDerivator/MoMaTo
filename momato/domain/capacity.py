"""Work patterns, available time, yearly availability, load and compare classes (R4.2, R4.3, R4.5).

Time is whole minutes; days and ratios are exact `Fraction`s, so sums partition exactly and classes
change at their boundaries and not a rounding step later.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from fractions import Fraction

from momato.domain.calendar import (
    WORKDAYS_PER_WEEK,
    Quarter,
    count_weekday,
    weekdays_between,
    year_workdays,
)

MINUTES_PER_HOUR = 60
STANDARD_WEEK_MINUTES = 40 * MINUTES_PER_HOUR  # the capacity factor is relative to this

# Load classes: ratio of a value to its capacity (R4.5).
LIGHT_BELOW = Fraction(40, 100)
COMFORTABLE_BELOW = Fraction(85, 100)
NEARLY_FULL_UP_TO = Fraction(102, 100)
# Compare classes: spent against planned.
OVER_ABOVE = Fraction(115, 100)
UNDER_BELOW = Fraction(85, 100)


@dataclass(frozen=True)
class WorkPattern:
    """Minutes worked per weekday, Monday to Friday (D-019). Default: 8 hours each day."""

    minutes: tuple[int, int, int, int, int] = (480, 480, 480, 480, 480)

    def __post_init__(self) -> None:
        if len(self.minutes) != WORKDAYS_PER_WEEK or any(m < 0 for m in self.minutes):
            raise ValueError("a work pattern is five non-negative numbers of minutes")

    @property
    def weekly_target_minutes(self) -> int:
        return sum(self.minutes)

    @property
    def capacity_factor(self) -> Fraction:
        return Fraction(self.weekly_target_minutes, STANDARD_WEEK_MINUTES)

    def target_minutes(self, d: date) -> int:
        """The day target: that weekday's minutes, 0 at weekends."""
        return self.minutes[d.weekday()] if d.weekday() < WORKDAYS_PER_WEEK else 0

    def is_working_day(self, d: date) -> bool:
        return self.target_minutes(d) > 0

    def working_days(self, start: date, end: date) -> int:
        """Weekdays of `start..end` with a target above zero."""
        return sum(
            count_weekday(weekday, start, end)
            for weekday, minutes in enumerate(self.minutes)
            if minutes > 0
        )

    def target_minutes_between(self, start: date, end: date) -> int:
        """The sum of the day targets over `start..end`."""
        return sum(
            minutes * count_weekday(weekday, start, end)
            for weekday, minutes in enumerate(self.minutes)
        )


def available_minutes(pattern: WorkPattern, start: date, end: date, time_off_minutes: int) -> int:
    """Time a person can work in a period: their day targets minus the time off booked in it."""
    return max(0, pattern.target_minutes_between(start, end) - time_off_minutes)


def year_availability_days(
    override: Fraction | None, pattern: WorkPattern, default_days: int
) -> Fraction:
    """Days a person can be planned in a year: the override, else the default × capacity factor."""
    if override is not None:
        return override
    return default_days * pattern.capacity_factor


def quarter_availability_days(year_days: Fraction, quarter: Quarter) -> Fraction:
    """A quarter's share of the year's availability, by workdays."""
    return year_days * quarter.workdays / year_workdays(quarter.year)


def period_availability_days(year_days: Fraction, start: date, end: date) -> Fraction:
    """The availability of a period within one calendar year, by workdays."""
    return year_days * weekdays_between(start, end) / year_workdays(start.year)


class LoadClass(StrEnum):
    EMPTY = "empty"
    LIGHT = "light"
    COMFORTABLE = "comfortable"
    NEARLY_FULL = "nearly_full"
    OVER = "over"


LOAD_LABELS = {
    LoadClass.EMPTY: "",
    LoadClass.LIGHT: "Light",
    LoadClass.COMFORTABLE: "Comfortable",
    LoadClass.NEARLY_FULL: "Nearly full",
    LoadClass.OVER: "Over capacity",
}


def load_class(value: Fraction | int, capacity: Fraction | int) -> LoadClass:
    """Classify `value` against `capacity` (both in the same unit); no capacity at all is over."""
    if value == 0:
        return LoadClass.EMPTY
    if capacity <= 0:
        return LoadClass.OVER
    ratio = Fraction(value) / Fraction(capacity)
    if ratio < LIGHT_BELOW:
        return LoadClass.LIGHT
    if ratio < COMFORTABLE_BELOW:
        return LoadClass.COMFORTABLE
    if ratio <= NEARLY_FULL_UP_TO:
        return LoadClass.NEARLY_FULL
    return LoadClass.OVER


class CompareClass(StrEnum):
    EMPTY = "empty"
    UNPLANNED = "unplanned"
    OVER = "over"
    UNDER = "under"
    ON_TRACK = "on_track"


COMPARE_LABELS = {
    CompareClass.EMPTY: "",
    CompareClass.UNPLANNED: "Unplanned",
    CompareClass.OVER: "Over",
    CompareClass.UNDER: "Under",
    CompareClass.ON_TRACK: "On track",
}


def compare_class(spent: Fraction | int, planned: Fraction | int) -> CompareClass:
    """Classify time spent against time planned (same unit)."""
    if spent == 0 and planned == 0:
        return CompareClass.EMPTY
    if planned == 0:
        return CompareClass.UNPLANNED
    ratio = Fraction(spent) / Fraction(planned)
    if ratio > OVER_ABOVE:
        return CompareClass.OVER
    if ratio < UNDER_BELOW:
        return CompareClass.UNDER
    return CompareClass.ON_TRACK
