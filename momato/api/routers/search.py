"""Search endpoints for pickers: projects and people, on the server as the user types."""

from typing import Annotated

from fastapi import APIRouter, Query

from momato.api.deps import Search
from momato.schemas.search import PersonHit, ProjectHit

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/projects")
def search_projects(
    service: Search,
    q: Annotated[str, Query(max_length=200)] = "",
    bookable: Annotated[bool, Query(description="only In preparation or In progress")] = False,
) -> list[ProjectHit]:
    return service.projects(q, bookable=bookable)


@router.get("/people")
def search_people(
    service: Search, q: Annotated[str, Query(max_length=200)] = ""
) -> list[PersonHit]:
    return service.people(q)
