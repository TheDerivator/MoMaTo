"""Project endpoints: list, counts, neighbours, one project, edits, tasks, planning, logbook."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from momato.api.deps import Planning, Projects, Tasks
from momato.domain.projects import ProjectStatus
from momato.schemas.projects import (
    LogPage,
    MemberAdd,
    Neighbours,
    PlannedCellSet,
    PlannedDaysGrid,
    ProjectCounts,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectUpdate,
    TaskCreate,
    TaskDeleted,
    TaskMove,
    TaskOut,
    TaskUpdate,
)
from momato.services.projects import PAGE_SIZE, ProjectFilters

router = APIRouter(prefix="/projects", tags=["projects"])


def list_filters(
    node: Annotated[int | None, Query(description="an org node: its whole branch")] = None,
    status_: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    q: Annotated[
        str, Query(max_length=200, description="name, number, coordinator, org node")
    ] = "",
    name: Annotated[str, Query(max_length=200)] = "",
    coordinator: Annotated[str, Query(max_length=200)] = "",
) -> ProjectFilters:
    return ProjectFilters(node=node, status=status_, q=q, name=name, coordinator=coordinator)


Filters = Annotated[ProjectFilters, Depends(list_filters)]


@router.get("")
def list_projects(
    service: Projects,
    filters: Filters,
    after: Annotated[int | None, Query(description="the last number of the previous page")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = PAGE_SIZE,
) -> ProjectPage:
    """One page of projects, highest number first (keyset paging)."""
    return service.page(filters, after, limit)


@router.get("/counts")
def project_counts(service: Projects, filters: Filters) -> ProjectCounts:
    """Counts per status and per org node (rolled up), for the same filters."""
    return service.counts(filters)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, service: Projects) -> ProjectOut:
    return service.create(body)


@router.get("/{number}")
def get_project(number: int, service: Projects) -> ProjectOut:
    return service.get(number)


@router.patch("/{number}")
def update_project(number: int, body: ProjectUpdate, service: Projects) -> ProjectOut:
    """Edit core fields and details. 409 when `version` is stale."""
    return service.update(number, body)


@router.delete("/{number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(number: int, service: Projects) -> None:
    service.delete(number)


@router.get("/{number}/neighbours")
def project_neighbours(number: int, service: Projects, filters: Filters) -> Neighbours:
    """Position and neighbours of a project in the list of the same filters (PP-1)."""
    return service.neighbours(number, filters)


@router.get("/{number}/log")
def project_log(
    number: int,
    service: Projects,
    filter_: Annotated[str | None, Query(alias="filter")] = None,
) -> LogPage:
    return service.log(number, filter_)


# ---------------------------------------------------------------- members and plans


@router.post("/{number}/members", status_code=status.HTTP_201_CREATED)
def add_member(number: int, body: MemberAdd, service: Projects) -> ProjectOut:
    return service.add_member(number, body.user_id)


@router.delete("/{number}/members/{user_id}")
def remove_member(number: int, user_id: int, service: Projects) -> ProjectOut:
    return service.remove_member(number, user_id)


@router.put("/{number}/plans/{plan_id}")
def link_plan(number: int, plan_id: int, service: Projects) -> ProjectOut:
    return service.link_plan(number, plan_id)


@router.delete("/{number}/plans/{plan_id}")
def unlink_plan(number: int, plan_id: int, service: Projects) -> ProjectOut:
    return service.unlink_plan(number, plan_id)


# ---------------------------------------------------------------- tasks


@router.get("/{number}/tasks")
def list_tasks(number: int, service: Tasks) -> list[TaskOut]:
    return service.for_project(number)


@router.post("/{number}/tasks", status_code=status.HTTP_201_CREATED)
def create_task(number: int, body: TaskCreate, service: Tasks) -> TaskOut:
    return service.create(number, body)


@router.patch("/{number}/tasks/{task_id}")
def update_task(number: int, task_id: int, body: TaskUpdate, service: Tasks) -> TaskOut:
    return service.update(number, task_id, body)


@router.post("/{number}/tasks/{task_id}/move")
def move_task(number: int, task_id: int, body: TaskMove, service: Tasks) -> list[TaskOut]:
    return service.move(number, task_id, body.direction)


@router.delete("/{number}/tasks/{task_id}")
def delete_task(number: int, task_id: int, service: Tasks) -> TaskDeleted:
    """Delete a task; its booked time moves to General."""
    return service.delete(number, task_id)


# ---------------------------------------------------------------- people & days


@router.get("/{number}/planned-days")
def planned_days(number: int, service: Planning) -> PlannedDaysGrid:
    return service.grid(number)


@router.put("/{number}/planned-days")
def set_planned_days(number: int, body: PlannedCellSet, service: Planning) -> PlannedDaysGrid:
    """Set one cell: days in steps of 0.5 up to the quarter's workdays; 0 clears it."""
    return service.set_cell(number, body)
