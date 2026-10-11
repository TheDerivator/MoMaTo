"""The number of SQL statements of a request does not depend on the number of projects (D-028).

The same requests are made on the sample's 200 projects and again with 1,800 more added; the
counts must be identical, so no endpoint loops over rows with a query each.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from momato.db.models import OrgNode, Project, ProjectMember, User
from momato.db.session import Database
from tests.api.test_projects import plan_id
from tests.helpers import count_statements

MANY = 1_800


def add_projects(database: Database, count: int) -> None:
    with database.session(write=True) as session:
        nodes = list(session.scalars(select(OrgNode.id).where(OrgNode.parent_id.is_not(None))))
        coordinator = session.scalar(select(User.id).where(User.username == "anna.claes"))
        assert coordinator is not None
        now = datetime(2026, 9, 1, tzinfo=UTC)
        session.execute(
            insert(Project),
            [
                {
                    "number": 20_000 + index,
                    "name": f"Bulk project {index} sensor",
                    "org_node_id": nodes[index % len(nodes)],
                    "status": "progress" if index % 3 else "idea",
                    "coordinator_id": coordinator,
                    "start_date": date(2026, 1, 1),
                    "end_date": date(2027, 1, 1),
                    "goal": "",
                    "priority": "medium",
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                }
                for index in range(count)
            ],
        )
        ids = list(session.scalars(select(Project.id).where(Project.number >= 20_000)))
        session.execute(
            insert(ProjectMember),
            [{"project_id": project_id, "user_id": coordinator} for project_id in ids],
        )


def statements(call: Callable[[], object]) -> int:
    with count_statements() as counter:
        call()
    return counter.count


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects",
        "/api/projects?after=4000&limit=50",
        "/api/projects?q=sensor&status=progress",
        "/api/projects/counts",
        "/api/projects/4102",
        "/api/projects/4102/neighbours",
        "/api/projects/4102/log",
        "/api/projects/4102/planned-days",
        "/api/search/projects?q=sensor",
        "/api/search/people?q=a",
        "/api/bootstrap",
    ],
)
def test_a_request_costs_the_same_with_ten_times_the_projects(
    anna: TestClient, sample_database: Database, path: str
) -> None:
    small = statements(lambda: anna.get(path))
    add_projects(sample_database, MANY)
    large = statements(lambda: anna.get(path))
    assert small == large, f"{path}: {small} statements on 200 projects, {large} on 2,000"
    assert small <= 20


def test_the_plan_overview_costs_the_same_with_more_projects(
    anna: TestClient, sample_database: Database
) -> None:
    plan = plan_id(anna, "Digital plant")
    path = f"/api/plans/{plan}/overview"
    small = statements(lambda: anna.get(path))
    add_projects(sample_database, MANY)
    assert statements(lambda: anna.get(path)) == small
    feed = f"/api/plans/{plan}/feed"
    assert statements(lambda: anna.get(feed)) <= 12
