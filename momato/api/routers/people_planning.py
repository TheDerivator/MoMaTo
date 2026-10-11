"""People planning endpoints: the table of people by bucket and one person's lines."""

from typing import Annotated

from fastapi import APIRouter, Query

from momato.api.deps import PeoplePlans
from momato.schemas.people_planning import PeoplePlanning, PersonLines

router = APIRouter(prefix="/people-planning", tags=["people planning"])


@router.get("")
def people_planning(
    service: PeoplePlans,
    node: Annotated[int | None, Query(description="an org node: its whole branch")] = None,
    mode: Annotated[str, Query(pattern="^(planned|spent|compare)$")] = "planned",
    period: Annotated[str, Query(pattern="^(week|month|year)$")] = "week",
    q: Annotated[str, Query(max_length=200, description="part of a name")] = "",
) -> PeoplePlanning:
    """Active people of the branch with their cells per bucket (PPL-1 – PPL-6)."""
    return service.overview(node, mode, period, q)


@router.get("/{person_id}")
def person_lines(
    person_id: int,
    service: PeoplePlans,
    mode: Annotated[str, Query(pattern="^(planned|spent|compare)$")] = "planned",
    period: Annotated[str, Query(pattern="^(week|month|year)$")] = "week",
) -> PersonLines:
    """One person's project, other work and time off lines for the same buckets (PPL-2, PPL-7)."""
    return service.person(person_id, mode, period)
