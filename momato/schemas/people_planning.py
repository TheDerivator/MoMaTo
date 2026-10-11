"""Shapes of the People planning endpoints: rows of people by bucket, and one person's lines
(PPL-1 – PPL-7)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from momato.schemas.projects import PersonRef

Mode = Literal["planned", "spent", "compare"]
PeriodName = Literal["week", "month", "year"]
Unit = Literal["hours", "days"]


class BucketOut(BaseModel):
    key: str  # "Q4/26", "Thu", "Wk 40", "Oct"
    sub: str  # "8 Oct", "Sep 28", "’25" or ""
    start: date
    end: date
    current: bool  # the quarter that contains today (Planned): its header is in accent


class CellOut(BaseModel):
    """One cell: the value in the unit of the view, what it is measured against, its class."""

    value: float  # planned days; time spent in hours (week) or days
    reference: float | None  # Planned, Spent: the capacity; Compare: the days planned
    cls: (
        str  # empty | light | comfortable | nearly_full | over (load); unplanned | under | on_track
    )
    # (compare; "over" is shared)


class TotalOut(BaseModel):
    value: float
    reference: float | None
    cls: str
    free: float | None  # Planned: the year's availability minus this year's planned days
    percent: int | None  # Compare: spent as a percentage of planned


class PersonRowOut(BaseModel):
    person: PersonRef
    org_node_id: int | None
    org_node_name: str | None
    cells: list[CellOut]
    total: TotalOut


class PeoplePlanning(BaseModel):
    mode: Mode
    period: PeriodName
    unit: Unit
    range_label: str
    buckets: list[BucketOut]
    rows: list[PersonRowOut]
    hidden_count: int  # people in the branch whose hours the caller may not see (Spent, Compare)
    total_count: int  # active people in the branch


class LineOut(BaseModel):
    """A line under a person: a project, other projects, other work or time off."""

    kind: Literal["project", "non_member", "other_projects", "other_work", "time_off"]
    number: int | None
    name: str
    status: str | None
    cells: list[CellOut]
    total: TotalOut


class PersonLines(BaseModel):
    person: PersonRef
    mode: Mode
    period: PeriodName
    unit: Unit
    buckets: list[BucketOut]
    lines: list[LineOut]
