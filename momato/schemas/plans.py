"""Shapes of the action plan endpoints: the plan, its overview by department, and its feed."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from momato.domain.projects import ProjectStatus
from momato.schemas.projects import PersonRef
from momato.schemas.reference import PlanSummary


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    owner_org_node_id: int
    coordinator_id: int
    hue: int = Field(ge=0, le=359)


class PlanUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    owner_org_node_id: int | None = None
    coordinator_id: int | None = None
    hue: int | None = Field(default=None, ge=0, le=359)


class PlanProjectAdd(BaseModel):
    number: int


class DaysMeter(BaseModel):
    planned: float
    logged: float
    expected: float
    logged_percent: float
    expected_percent: float


class PlanProject(BaseModel):
    """A project row of the timeline table (AP-5)."""

    number: int
    name: str
    status: ProjectStatus
    start_date: date
    end_date: date
    coordinator: PersonRef
    goal: str
    days: DaysMeter


class PlanGroup(BaseModel):
    """A top-level department's projects within the plan."""

    org_node_id: int
    name: str
    is_owner: bool
    projects: list[PlanProject]
    status_counts: dict[ProjectStatus, int]
    start_date: date
    end_date: date
    days: DaysMeter


class PlanOverview(BaseModel):
    plan: PlanSummary
    owner_name: str
    coordinator: PersonRef
    department_count: int  # "includes projects from 3 departments"
    project_count: int
    days: DaysMeter  # the totals card (AP-4)
    groups: list[PlanGroup]  # the owner's group first


class FeedItem(BaseModel):
    kind: str  # "remark" or "log"
    at: datetime
    project_number: int
    project_name: str
    actor: PersonRef
    tab: str  # "remarks" or "logbook": where the item opens
    excerpt: str | None  # a remark's plain text, three lines at most
    field: str | None  # a logbook change's field label
    from_value: str | None
    to_value: str | None


class PlanFeed(BaseModel):
    items: list[FeedItem]
