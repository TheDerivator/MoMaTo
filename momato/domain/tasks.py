"""Task status, slippage, project timeline text and the standard phases (R4.6, PG-5, PG-6).

Progress is entered by hand, 0 to 100 (D-008); the status is derived from it and the dates.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from fractions import Fraction

from momato.domain.formatting import format_date, round_half_up

FULL_PROGRESS = 100


class TaskStatus(StrEnum):
    DONE = "done"
    RUNNING = "running"
    PLANNED = "planned"


STATUS_LABELS = {
    TaskStatus.DONE: "Done",
    TaskStatus.RUNNING: "Running",
    TaskStatus.PLANNED: "Planned",
}


def task_status(progress: int, planned_start: date, today: date) -> TaskStatus:
    """Done at 100 %; Running once progress is above 0 or the start has come; else Planned."""
    if progress >= FULL_PROGRESS:
        return TaskStatus.DONE
    if progress > 0 or planned_start <= today:
        return TaskStatus.RUNNING
    return TaskStatus.PLANNED


def is_slipped(planned_end: date, revised_end: date | None) -> bool:
    return revised_end is not None and revised_end > planned_end


def effective_end(planned_end: date, revised_end: date | None) -> date:
    return revised_end if revised_end is not None else planned_end


def status_text(status: TaskStatus, progress: int) -> str:
    """ "Where we are" (OV-2): running tasks read "45% · running", the others their status."""
    if status is TaskStatus.RUNNING:
        return f"{progress}% · running"
    return STATUS_LABELS[status]


def timeline_percent(start: date, end: date, today: date) -> int:
    """How much of the project's span is behind us, rounded; 100 for a one-day span on its day."""
    span = (end - start).days
    if span <= 0:
        return 100
    elapsed = min(max((today - start).days, 0), span)
    return round_half_up(Fraction(elapsed * 100, span))


def timeline_text(start: date, end: date, today: date) -> str:
    """ "Starts 3 Nov 2025", "Ended 19 Dec 2025" or "45% of the timeline behind us"."""
    if today < start:
        return f"Starts {format_date(start)}"
    if today > end:
        return f"Ended {format_date(end)}"
    return f"{timeline_percent(start, end, today)}% of the timeline behind us"


def validate_task_dates(planned_start: date, planned_end: date, revised_end: date | None) -> None:
    """PG-5: an end is not before its start, and a revised end is after the planned end."""
    if planned_end < planned_start:
        raise ValueError("The end of a task cannot be before its start.")
    if revised_end is not None and revised_end <= planned_end:
        raise ValueError("A revised end must be after the planned end.")


@dataclass(frozen=True)
class TemplateTask:
    """One phase of a profile's task template: where it sits in the project span, as fractions."""

    name: str
    start: Fraction  # 0 is the project's start, 1 its end
    end: Fraction
    milestone: bool = False


@dataclass(frozen=True)
class PlannedTask:
    name: str
    planned_start: date
    planned_end: date
    is_milestone: bool


def _at(start: date, span_days: int, fraction: Fraction) -> date:
    return start + timedelta(days=round_half_up(span_days * fraction))


def tasks_from_template(
    template: Sequence[TemplateTask], start: date, end: date
) -> list[PlannedTask]:
    """Spread the template's phases over the project span by their fractions."""
    span = max((end - start).days, 0)
    return [
        PlannedTask(t.name, _at(start, span, t.start), _at(start, span, t.end), t.milestone)
        for t in template
    ]
