"""Shapes of the project endpoints: list rows and pages, counts, the project, tasks, planning."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from momato.domain.projects import Priority, ProjectStatus
from momato.schemas.common import Name200


class PersonRef(BaseModel):
    id: int
    name: str
    hue: int
    job_title: str | None = None


class ProjectRow(BaseModel):
    """A row of the project list (PL-4)."""

    number: int
    name: str
    org_node_id: int
    org_node_name: str
    status: ProjectStatus
    start_date: date
    end_date: date
    coordinator: PersonRef
    members: list[PersonRef]  # the people involved other than the coordinator, at most three


class ProjectPage(BaseModel):
    items: list[ProjectRow]
    total: int  # all projects matching the filters, not only this page
    next_after: int | None  # pass as `after` to get the next page; None at the end


class ProjectCounts(BaseModel):
    """Counts for the status chips and the tree (PL-2, SH-3), from the server."""

    statuses: dict[ProjectStatus, int]  # follow branch, search and column filters
    nodes: dict[int, int]  # per org node, rolled up the tree; hidden statuses left out
    total: int  # what the header says: the list's total


class Neighbours(BaseModel):
    """Where a project is in the filtered list, for the "3 of 214" stepper (PP-1)."""

    position: int | None  # 1-based, highest number first; None when not in the list
    total: int
    previous: int | None  # the project above it (a higher number)
    next: int | None  # the project below it
    in_list: bool


class TaskOut(BaseModel):
    id: int
    position: int
    name: str
    planned_start: date
    planned_end: date
    revised_end: date | None
    is_milestone: bool
    progress: int
    status: str  # derived: done, running, planned (R4.6)
    status_text: str  # "45% · running", "Done", "Planned"
    slipped: bool
    effective_end: date
    booked_minutes: int
    version: int


class DaysOut(BaseModel):
    planned: float
    logged: float
    expected: float
    logged_percent: float
    expected_percent: float


class ProjectOut(BaseModel):
    number: int
    name: str
    org_node_id: int
    org_node_name: str
    status: ProjectStatus
    start_date: date
    end_date: date
    goal: str
    priority: Priority
    coordinator: PersonRef
    members: list[PersonRef]  # all, the coordinator first
    plan_ids: list[int]
    details: dict[str, Any]  # profile detail values by field key
    timeline_text: str
    tasks: list[TaskOut]
    days: DaysOut
    remark_count: int
    log_count: int
    created_at: datetime
    updated_at: datetime
    version: int
    can_edit: bool
    can_comment: bool
    can_delete: bool


class ProjectCreate(BaseModel):
    name: Name200
    org_node_id: int
    coordinator_id: int | None = None  # default: the caller
    start_date: date
    end_date: date
    status: ProjectStatus = ProjectStatus.IDEA
    goal: str = Field(default="", max_length=20_000)
    priority: Priority = Priority.MEDIUM
    use_template: bool = False  # "Start with the standard phases" (PG-6)

    @field_validator("name")
    @classmethod
    def _stripped(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("a name is required")
        return value


class ProjectUpdate(BaseModel):
    """A partial edit of the core fields and details; `version` is the one the editor loaded."""

    version: int
    name: Name200 | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    coordinator_id: int | None = None
    org_node_id: int | None = None
    goal: str | None = Field(default=None, max_length=20_000)
    priority: Priority | None = None
    details: dict[str, Any] | None = None  # field key → value (None clears it)


class MemberAdd(BaseModel):
    user_id: int


class TaskCreate(BaseModel):
    name: Name200
    planned_start: date
    planned_end: date
    revised_end: date | None = None
    is_milestone: bool = False
    progress: int = Field(default=0, ge=0, le=100)


class TaskUpdate(BaseModel):
    version: int
    name: Name200 | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    revised_end: date | None = None
    clear_revised_end: bool = False  # distinguishes "no revised end" from "leave as it is"
    is_milestone: bool | None = None
    progress: int | None = Field(default=None, ge=0, le=100)


class TaskMove(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class TaskDeleted(BaseModel):
    moved_minutes: int  # booked time that went to General


class PlanCell(BaseModel):
    """One person × quarter cell of People & days (PD-2)."""

    quarter_start: date
    planned: float
    logged: float
    upcoming: bool  # the quarter starts after today


class PlanRow(BaseModel):
    person: PersonRef
    is_coordinator: bool
    is_member: bool  # False: booked time without being a member (PD-5)
    cells: list[PlanCell]
    planned_total: float
    logged_total: float


class PlannedDaysGrid(BaseModel):
    quarters: list[date]  # first day of each column
    workdays: list[int]  # the working days of each quarter: the most a cell can hold (PD-3)
    rows: list[PlanRow]  # members, coordinator first
    also_booked: list[PlanRow]  # non-members with booked time, logged only
    total_planned: float
    total_logged: float
    hours_per_day: int


class PlannedCellSet(BaseModel):
    user_id: int
    quarter_start: date
    days: float = Field(ge=0)


class LogEntryOut(BaseModel):
    id: int
    at: datetime
    actor: PersonRef
    field: str
    field_label: str
    hue: int
    from_value: str | None
    to_value: str | None
    via: str | None = None  # the API token it was done through (TOK-3)


class LogPage(BaseModel):
    items: list[LogEntryOut]
    total: int  # for the chosen filter
    count: int  # all entries, for the tab's count (LB-2 shows the full count)
