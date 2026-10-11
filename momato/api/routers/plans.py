"""Action plan endpoints: list, manage, link projects, overview and feed (AP-1..AP-8)."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from momato.api.deps import Plans
from momato.schemas.plans import (
    PlanCreate,
    PlanFeed,
    PlanOverview,
    PlanProjectAdd,
    PlanUpdate,
)
from momato.schemas.reference import PlanSummary

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("")
def list_plans(service: Plans) -> list[PlanSummary]:
    return service.list()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreate, service: Plans) -> PlanSummary:
    return service.create(body)


@router.patch("/{plan_id}")
def update_plan(plan_id: int, body: PlanUpdate, service: Plans) -> PlanSummary:
    return service.update(plan_id, body)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, service: Plans) -> None:
    service.delete(plan_id)


@router.get("/{plan_id}/overview")
def plan_overview(plan_id: int, service: Plans) -> PlanOverview:
    """Totals and the timeline table grouped by department, the owner's first."""
    return service.overview(plan_id)


@router.get("/{plan_id}/feed")
def plan_feed(
    plan_id: int,
    service: Plans,
    project: Annotated[int | None, Query(description="only this project's items")] = None,
) -> PlanFeed:
    return service.feed(plan_id, project)


@router.post("/{plan_id}/projects", status_code=status.HTTP_201_CREATED)
def add_project(plan_id: int, body: PlanProjectAdd, service: Plans) -> PlanSummary:
    return service.add_project(plan_id, body.number)


@router.delete("/{plan_id}/projects/{number}")
def remove_project(plan_id: int, number: int, service: Plans) -> PlanSummary:
    return service.remove_project(plan_id, number)
