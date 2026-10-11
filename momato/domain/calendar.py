"""Calendar rules: ISO weeks, quarters, workdays, spent buckets, timeline windows (R4.1, R4.11/12).

Weeks are ISO weeks (Monday to Sunday, numbered per ISO 8601); working days are Monday to Friday;
quarters are calendar quarters, written `Q4/26`. There is no holiday calendar (D-019).
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from momato.domain.formatting import (
    MONTHS_LONG,
    WEEKDAYS_SHORT,
    format_short_date,
)

WORKDAYS_PER_WEEK = 5

_WEEK_LABEL = re.compile(r"(\d{4})-W(\d{2})")


def is_weekday(d: date) -> bool:
    return d.weekday() < WORKDAYS_PER_WEEK


def weekdays_between(start: date, end: date) -> int:
    """Monday-to-Friday days in `start..end` inclusive (0 when `end` is before `start`)."""
    if end < start:
        return 0
    total = (end - start).days + 1
    full_weeks, rest = divmod(total, 7)
    first = start.weekday()
    extra = sum(1 for i in range(rest) if (first + i) % 7 < WORKDAYS_PER_WEEK)
    return full_weeks * WORKDAYS_PER_WEEK + extra


def count_weekday(weekday: int, start: date, end: date) -> int:
    """How many days of `start..end` inclusive fall on `weekday` (Monday is 0)."""
    if end < start:
        return 0
    span = (end - start).days
    offset = (weekday - start.weekday()) % 7
    return 0 if offset > span else (span - offset) // 7 + 1


@dataclass(frozen=True, order=True)
class IsoWeek:
    year: int  # the ISO year, which differs from the calendar year around New Year
    week: int

    @classmethod
    def of(cls, d: date) -> IsoWeek:
        iso = d.isocalendar()
        return cls(iso.year, iso.week)

    @classmethod
    def parse(cls, label: str) -> IsoWeek:
        """`2026-W41`; raises ValueError for anything else, including weeks the year lacks."""
        match = _WEEK_LABEL.fullmatch(label)
        if match is None:
            raise ValueError(f"not an ISO week: {label!r}")
        year, week = int(match.group(1)), int(match.group(2))
        date.fromisocalendar(year, week, 1)  # ValueError when the year has no such week
        return cls(year, week)

    @property
    def label(self) -> str:
        return f"{self.year}-W{self.week:02d}"

    @property
    def monday(self) -> date:
        return date.fromisocalendar(self.year, self.week, 1)

    @property
    def friday(self) -> date:
        return self.monday + timedelta(days=4)

    @property
    def sunday(self) -> date:
        return self.monday + timedelta(days=6)

    @property
    def days(self) -> tuple[date, date, date, date, date]:
        """Monday to Friday."""
        m = self.monday
        return tuple(m + timedelta(days=i) for i in range(5))  # pyright: ignore[reportReturnType]

    def shifted(self, weeks: int) -> IsoWeek:
        return IsoWeek.of(self.monday + timedelta(weeks=weeks))


@dataclass(frozen=True, order=True)
class Quarter:
    year: int
    number: int  # 1 to 4

    @classmethod
    def containing(cls, d: date) -> Quarter:
        return cls(d.year, (d.month - 1) // 3 + 1)

    @classmethod
    def starting(cls, d: date) -> Quarter:
        """The quarter that starts on `d`; ValueError when `d` is not a quarter's first day."""
        quarter = cls.containing(d)
        if quarter.start != d:
            raise ValueError(f"{d} is not the first day of a quarter")
        return quarter

    @property
    def start(self) -> date:
        return date(self.year, (self.number - 1) * 3 + 1, 1)

    @property
    def end(self) -> date:
        following = self.shifted(1)
        return following.start - timedelta(days=1)

    @property
    def label(self) -> str:
        return f"Q{self.number}/{self.year % 100:02d}"

    @property
    def workdays(self) -> int:
        return weekdays_between(self.start, self.end)

    def shifted(self, quarters: int) -> Quarter:
        index = self.year * 4 + (self.number - 1) + quarters
        return Quarter(index // 4, index % 4 + 1)


def quarters_overlapping(start: date, end: date) -> list[Quarter]:
    """Every calendar quarter that has a day in `start..end`, in order."""
    if end < start:
        return []
    first, last = Quarter.containing(start), Quarter.containing(end)
    return [
        first.shifted(i)
        for i in range((last.year - first.year) * 4 + last.number - first.number + 1)
    ]


def year_workdays(year: int) -> int:
    return weekdays_between(date(year, 1, 1), date(year, 12, 31))


# ---------------------------------------------------------------- buckets (R4.11)


class Period(StrEnum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Unit(StrEnum):
    HOURS = "hours"
    DAYS = "days"


@dataclass(frozen=True)
class Bucket:
    key: str  # column title: "Mon", "Wk 37", "Oct", "Q4/26"
    sub: str  # second line: "28 Sep", "’25", "" for quarters
    start: date
    end: date


@dataclass(frozen=True)
class BucketSet:
    buckets: tuple[Bucket, ...]
    range_label: str
    unit: Unit


def planned_buckets(today: date) -> BucketSet:
    """Planned mode: the eight quarters of the current and the next year (PPL-3)."""
    first = Quarter(today.year, 1)
    quarters = [first.shifted(i) for i in range(8)]
    buckets = tuple(Bucket(q.label, "", q.start, q.end) for q in quarters)
    return BucketSet(buckets, f"Quarters {today.year} – {today.year + 1} · days", Unit.DAYS)


def current_quarter(today: date) -> Quarter:
    return Quarter.containing(today)


def spent_buckets(period: Period, today: date) -> BucketSet:
    """Spent and Compare: the last full weeks or months, all ended before today's week or month."""
    this_week = IsoWeek.of(today)
    if period is Period.WEEK:
        week = this_week.shifted(-1)
        buckets = tuple(
            Bucket(WEEKDAYS_SHORT[i], format_short_date(day), day, day)
            for i, day in enumerate(week.days)
        )
        label = (
            f"Week {week.week} · {format_short_date(week.monday)} – "
            f"{format_short_date(week.friday)} {week.friday.year} · hours"
        )
        return BucketSet(buckets, label, Unit.HOURS)
    if period is Period.MONTH:
        weeks = [this_week.shifted(-n) for n in (4, 3, 2, 1)]
        buckets = tuple(
            Bucket(f"Wk {w.week}", format_short_date(w.monday), w.monday, w.friday) for w in weeks
        )
        label = (
            f"Weeks {weeks[0].week} – {weeks[-1].week} · {format_short_date(weeks[0].monday)} – "
            f"{format_short_date(weeks[-1].friday)} {weeks[-1].friday.year} · days"
        )
        return BucketSet(buckets, label, Unit.DAYS)
    first_of_this_month = date(today.year, today.month, 1)
    months: list[date] = []
    cursor = first_of_this_month
    for _ in range(12):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        months.append(cursor)
    months.reverse()
    buckets = tuple(
        Bucket(
            MONTHS_LONG[m.month - 1][:3],
            f"’{m.year % 100:02d}",
            m,
            _next_month(m) - timedelta(days=1),
        )
        for m in months
    )
    label = (
        f"{MONTHS_LONG[months[0].month - 1]} {months[0].year} – "
        f"{MONTHS_LONG[months[-1].month - 1]} {months[-1].year} · days"
    )
    return BucketSet(buckets, label, Unit.DAYS)


def _next_month(first_of_month: date) -> date:
    return (first_of_month + timedelta(days=32)).replace(day=1)


# ---------------------------------------------------------------- timeline window (R4.12, D-029)


def timeline_window(today: date) -> tuple[date, date]:
    """From 1 January of last year to 31 December of next year."""
    return date(today.year - 1, 1, 1), date(today.year + 1, 12, 31)
