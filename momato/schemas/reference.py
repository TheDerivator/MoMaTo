"""The bootstrap document: everything the frontend needs once, never any projects (SH-12)."""

from datetime import date

from pydantic import BaseModel

from momato.schemas.auth import Me
from momato.schemas.timesheet import WeekCard


class OrgNodeOut(BaseModel):
    id: int
    parent_id: int | None
    name: str
    position: int
    is_department: bool


class PersonOut(BaseModel):
    id: int
    name: str
    job_title: str | None
    org_node_id: int | None
    hue: int
    active: bool  # works here: false once deactivated (a suspended sign-in still counts, D-057)
    work_minutes: list[int]  # Monday to Friday


class StatusOut(BaseModel):
    key: str
    label: str
    hue: int
    gray: bool
    hidden: bool  # left out of the list and its counts unless its chip is selected (PL-2)


class PriorityOut(BaseModel):
    key: str
    label: str


class PlanSummary(BaseModel):
    id: int
    name: str
    description: str
    owner_org_node_id: int
    coordinator_id: int
    hue: int
    position: int
    project_count: int  # projects the caller may see (AP-8)
    version: int


class FieldOut(BaseModel):
    key: str
    label: str
    type: str | None  # a detail field's type (DT-2); None for a core row
    core: str | None  # number, department or priority
    choices: list[str]


class CardOut(BaseModel):
    key: str
    title: str
    fields: list[FieldOut]


class CategoryOut(BaseModel):
    key: str
    label: str
    kind: str


class TemplateTaskOut(BaseModel):
    name: str
    start: float
    end: float
    milestone: bool


class ProfileOut(BaseModel):
    name: str
    cards: list[CardOut]
    categories: list[CategoryOut]
    task_template: list[TemplateTaskOut]
    hours_per_day: int
    day_cap_minutes: int
    timesheet_step_minutes: int
    available_days_per_year: int
    other_work_share: float
    first_project_number: int


class Bootstrap(BaseModel):
    version: str
    today: date
    me: Me
    org: list[OrgNodeOut]
    people: list[PersonOut]
    statuses: list[StatusOut]
    priorities: list[PriorityOut]
    plans: list[PlanSummary]
    profile: ProfileOut
    week_card: WeekCard | None  # the current week of the caller; None without a timesheet
