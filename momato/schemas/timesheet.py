"""Shapes of the timesheet endpoints: a week with its lines and cells, the week's state and the
week card of the sidebar (TS-1 – TS-15, R4.8, R4.9)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DayOut(BaseModel):
    index: int  # 0 is Monday
    date: date
    target_minutes: int  # 0 on a day the person does not work
    minutes: int  # everything booked that day, time off included
    full: bool
    open: bool
    tag: Literal["done", "today", "next", "open", ""]  # ✓, Today, Next, Open (R4.9)
    fill: float  # 0 to 1: how much of the day's target is booked


class WeekStateOut(BaseModel):
    """What R4.9 says about a week: its state and the texts of the week card and the headline."""

    state: Literal["submitted", "open", "full", "partial", "fresh"]
    full_days: int
    working_days: int
    open_days: list[int]
    total_minutes: int
    target_minutes: int
    title: str
    cta: str
    headline: str
    subline: str


class WeekCard(BaseModel):
    """The current week in the sidebar (SH-2, TS-15)."""

    week: str  # "2026-W41"
    week_number: int
    today_index: int  # Monday 0; 4 on a weekend
    days: list[DayOut]
    submitted: bool
    state: WeekStateOut


class TaskChoice(BaseModel):
    """A choice of the task picker: a task, *General*, or a category (TS-6)."""

    key: str  # "task:12", "general" or a category key
    name: str
    status: Literal["done", "running", "planned"] | None  # a task's derived status
    position: int  # the project's task order; General and categories are last


class LineOut(BaseModel):
    """One card of the week: a project, Other work or Time off (TS-4)."""

    key: str  # "project:4102", "other_work" or "time_off"
    kind: Literal["project", "other_work", "time_off"]
    number: int | None  # the project's number
    name: str
    status: str | None  # the project's status key
    planned_minutes: float | None  # None: nothing planned (an unplanned project, Time off)
    unplanned: bool
    choices: list[TaskChoice]
    minutes: dict[str, list[int]]  # choice key → minutes Monday to Friday (zero rows left out)
    # choice key → per weekday the API token a cell was last written through (None: by hand)
    via: dict[str, list[str | None]] = {}


class TimesheetOut(BaseModel):
    week: str
    iso_year: int
    iso_week: int
    monday: date
    friday: date
    is_current: bool
    today_index: int  # Monday 0 in the current week, 7 for a past week (R4.9)
    previous: str | None  # the week before; None never (history is unlimited)
    next: str | None  # None in the current week
    days: list[DayOut]
    lines: list[LineOut]
    submitted: bool
    submitted_at: datetime | None
    state: WeekStateOut
    step_minutes: int
    cap_minutes: int
    hours_per_day: int
    other_work_share: float


class CellSet(BaseModel):
    """Set the minutes of one cell to an absolute value (TS-9): repeating it changes nothing."""

    day: date
    line: str
    task: str
    minutes: int = Field(ge=0)
