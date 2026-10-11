"""Timesheet rules: the + and − booking steps (R4.8) and the states of a week (R4.9).

A day's time is a mapping from cells `(line, task)` to minutes. The browser mirrors these rules in
`static/js/lib/timesheet.js` (instant feedback); both are tested against the same fixture tables.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from momato.domain.calendar import WORKDAYS_PER_WEEK
from momato.domain.formatting import WEEKDAYS_LONG, format_hours

type Cell = tuple[str, str]  # (line key, task key); a project's General entry has its own task key

PAST_WEEK = 7  # the "today index" of a week that is over: every working day lies behind it
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five")


@dataclass(frozen=True)
class BookingResult:
    day: Mapping[Cell, int]
    cell: Cell | None  # the cell that changed; None when nothing happened


def add_step(
    day: Mapping[Cell, int], line: str, task: str, *, step: int, cap: int
) -> BookingResult:
    """+: a step on the selected task, unless the day (time off too) would pass the cap."""
    if sum(day.values()) + step > cap:
        return BookingResult(day, None)
    cell = (line, task)
    return BookingResult({**day, cell: day.get(cell, 0) + step}, cell)


def remove_step(
    day: Mapping[Cell, int], line: str, task: str, *, step: int, picker_order: Sequence[str]
) -> BookingResult:
    """−: one step from the selected task, else from the first task of the line that has time."""
    for candidate in (task, *(t for t in picker_order if t != task)):
        cell = (line, candidate)
        value = day.get(cell, 0)
        if value > 0:
            return BookingResult({**day, cell: max(0, value - step)}, cell)
    return BookingResult(day, None)


# ---------------------------------------------------------------- week states


class DayTag(StrEnum):
    DONE = "done"  # shown as ✓
    TODAY = "today"
    NEXT = "next"
    OPEN = "open"
    NONE = ""


class WeekState(StrEnum):
    SUBMITTED = "submitted"
    OPEN = "open"
    FULL = "full"
    PARTIAL = "partial"
    FRESH = "fresh"


@dataclass(frozen=True)
class DayView:
    index: int  # 0 is Monday
    target: int  # minutes
    minutes: int
    working: bool
    full: bool
    open: bool
    tag: DayTag
    fill: Fraction  # 0 to 1: how much of the day target is booked


@dataclass(frozen=True)
class WeekView:
    days: tuple[DayView, ...]
    state: WeekState
    full_days: int
    working_days: int
    open_days: tuple[int, ...]
    total_minutes: int
    target_minutes: int
    title: str
    cta: str
    headline: str
    subline: str


def _capitalised(word: str) -> str:
    return word[0].upper() + word[1:]


def _open_day_names(open_days: Sequence[int]) -> str:
    if len(open_days) == 1:
        return WEEKDAYS_LONG[open_days[0]]
    if len(open_days) == 2:
        return f"{WEEKDAYS_LONG[open_days[0]]} and {WEEKDAYS_LONG[open_days[1]]}"
    return f"{len(open_days)} days"


def _hours_number(minutes: int) -> str:
    return format_hours(minutes).removesuffix(" h")


def day_views(
    targets: Sequence[int], booked: Sequence[int], today_index: int
) -> tuple[DayView, ...]:
    """Full / open / tag of each weekday. `today_index` is Monday 0 in the current week, 7 later."""
    views: list[DayView] = []
    for index, (target, minutes) in enumerate(zip(targets, booked, strict=True)):
        working = target > 0
        full = working and minutes >= target
        open_ = working and index < today_index - 1 and not full
        if not working:
            tag = DayTag.NONE
        elif full:
            tag = DayTag.DONE
        elif index == today_index:
            tag = DayTag.TODAY
        elif index > today_index:
            tag = DayTag.NEXT
        elif open_:
            tag = DayTag.OPEN
        else:
            tag = DayTag.NONE
        fill = min(Fraction(1), Fraction(minutes, target)) if working else Fraction(0)
        views.append(DayView(index, target, minutes, working, full, open_, tag, fill))
    return tuple(views)


def week_view(
    targets: Sequence[int],
    booked: Sequence[int],
    *,
    today_index: int,
    submitted: bool,
    week_number: int,
) -> WeekView:
    """The week's state with the texts of the week card (TS-15) and the headline (TS-2)."""
    if len(targets) != WORKDAYS_PER_WEEK or len(booked) != WORKDAYS_PER_WEEK:
        raise ValueError("a week has five working days")
    days = day_views(targets, booked, today_index)
    working = [d for d in days if d.working]
    full_days = sum(1 for d in working if d.full)
    open_days = tuple(d.index for d in working if d.open)
    total, target = sum(booked), sum(targets)
    logged = f"{_hours_number(total)} of {_hours_number(target)} h"

    if submitted:
        state = WeekState.SUBMITTED
        title, cta = f"Week {week_number} submitted ✓", "View week →"
        headline = "Week submitted"
        hours = _hours_number(total)
        subline = f"{hours} {'hour' if hours == '1' else 'hours'} logged. Enjoy the weekend."
    elif open_days:
        state = WeekState.OPEN
        names = _open_day_names(open_days)
        title, cta = f"{names} still open", "Catch up →"
        headline = f"Let's catch up on {names}"
        subline = f"Catching up takes a minute. {logged} logged so far."
    elif working and full_days == len(working):
        state = WeekState.FULL
        title, cta = "Full week done!", "Submit week →"
        headline = "Your week is full. Ready to submit?"
        count = NUMBER_WORDS[len(working)]
        verb = "day is" if len(working) == 1 else "days are"
        subline = f"All {count} {verb} in. One tap to submit."
    else:
        cta = "Keep going →"
        if full_days:
            state = WeekState.PARTIAL
            count = _capitalised(NUMBER_WORDS[full_days])
            noun = "day" if full_days == 1 else "days"
            title = f"{count} {noun} done!"
            headline = f"{count} {noun} done, {len(working) - full_days} to go"
        else:
            state = WeekState.FRESH
            title, headline = "Fresh week, let's go", "Let's fill in your week"
        next_up = next((d for d in working if not d.full), None)
        subline = f"{logged} logged."
        if next_up is not None:
            subline += f" Next up: {WEEKDAYS_LONG[next_up.index]}."
    return WeekView(
        days=days,
        state=state,
        full_days=full_days,
        working_days=len(working),
        open_days=open_days,
        total_minutes=total,
        target_minutes=target,
        title=title,
        cta=cta,
        headline=headline,
        subline=subline,
    )
