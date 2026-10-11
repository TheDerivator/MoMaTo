"""Timesheet endpoints: a week of the caller's own time, setting a cell, submitting."""

from fastapi import APIRouter

from momato.api.deps import Timesheets
from momato.schemas.timesheet import CellSet, TimesheetOut

router = APIRouter(prefix="/timesheet", tags=["timesheet"])


@router.get("")
def current_week(service: Timesheets) -> TimesheetOut:
    """The current ISO week."""
    return service.week(None)


@router.get("/{week}")
def get_week(week: str, service: Timesheets) -> TimesheetOut:
    """A week as `2026-W41`; weeks that have not started are refused (422)."""
    return service.week(week)


@router.put("/{week}/cells")
def set_cell(week: str, body: CellSet, service: Timesheets) -> TimesheetOut:
    """Set one cell (day, line, task) to an absolute number of minutes (TS-9, R4.8)."""
    return service.set_cell(week, body)


@router.post("/{week}/submit")
def submit_week(week: str, service: Timesheets) -> TimesheetOut:
    """Mark the week submitted (D-007); changing any time of it reopens it."""
    return service.submit(week)
