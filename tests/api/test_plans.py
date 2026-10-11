"""Action plans: list, manage, link projects, the overview by department, and the feed.

[AP-1] [AP-4] [AP-5] [AP-6] [AP-7] [AP-8] D-031
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from momato.db.models import (
    ActionPlan,
    ActionPlanProject,
    DefaultGrant,
    LogEntry,
    Project,
    User,
)
from momato.db.session import Database
from momato.domain.access import Scope
from momato.services.sample_data import PlanSpec, Sample
from tests.api.conftest import ClientFactory, grant
from tests.api.test_projects import log_of, node_id, person_id, plan_id


def plan_spec(sample: Sample, name: str) -> PlanSpec:
    return next(p for p in sample.plans if p.name == name)


def top(node_path: str) -> str:
    return node_path.split("/")[0]


# ---------------------------------------------------------------- list


def test_the_plans_are_listed_with_their_visible_project_counts(
    anna: TestClient, sample: Sample
) -> None:
    plans = anna.get("/api/plans").json()
    assert [p["name"] for p in plans] == [p.name for p in sample.plans]
    for plan in plans:
        assert plan["project_count"] == len(plan_spec(sample, plan["name"]).projects)
    assert {"owner_org_node_id", "coordinator_id", "hue", "position", "version"} <= set(plans[0])


def test_a_visitor_gets_401(clients: ClientFactory) -> None:
    visitor = clients()
    assert visitor.get("/api/plans").status_code == 401
    assert visitor.get("/api/plans/1/overview").status_code == 401
    assert visitor.get("/api/plans/1/feed").status_code == 401


# ---------------------------------------------------------------- manage


def plan_body(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "  Quality first  ",
        "description": "Everything about quality.",
        "owner_org_node_id": node_id(client, "Quality"),
        "coordinator_id": person_id(client, "Anna Claes"),
        "hue": 200,
    }
    body.update(overrides)
    return body


def test_creating_a_plan_needs_plan_manage_in_the_owners_branch(
    clients: ClientFactory, sample_database: Database
) -> None:
    viewer = clients("anna.claes")
    assert viewer.post("/api/plans", json=plan_body(viewer)).status_code == 403
    assert clients().post("/api/plans", json=plan_body(viewer)).status_code == 401
    grant(sample_database, "anna.claes", "project_admin", Scope.node(node_id(viewer, "STL")))
    manager = clients("anna.claes")
    created = manager.post("/api/plans", json=plan_body(manager))
    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["hue"], body["project_count"], body["version"]) == (
        "Quality first", 200, 0, 1,
    )  # fmt: skip
    elsewhere = manager.post(
        "/api/plans", json=plan_body(manager, owner_org_node_id=node_id(manager, "Hot rolling"))
    )
    assert elsewhere.status_code == 403
    assert any(p["name"] == "Quality first" for p in manager.get("/api/plans").json())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"owner_org_node_id": 999_999}, "no org node"),
        ({"coordinator_id": 999_999}, "no such coordinator"),
    ],
)
def test_plan_references_are_validated(
    admin: TestClient, override: dict[str, Any], message: str
) -> None:
    response = admin.post("/api/plans", json=plan_body(admin, **override))
    assert response.status_code == 422
    assert message in response.json()["message"]
    assert admin.post("/api/plans", json=plan_body(admin, hue=400)).status_code == 422
    assert admin.post("/api/plans", json=plan_body(admin, name="")).status_code == 422


def test_updating_a_plan_checks_the_version_and_the_new_owner(
    clients: ClientFactory, sample_database: Database
) -> None:
    stl = node_id(clients("anna.claes"), "STL")
    grant(sample_database, "anna.claes", "project_admin", Scope.node(stl))
    manager = clients("anna.claes")
    created = manager.post("/api/plans", json=plan_body(manager)).json()
    url = f"/api/plans/{created['id']}"
    updated = manager.patch(url, json={"version": 1, "name": "Renamed", "hue": 10})
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["version"]) == ("Renamed", 2)
    stale = manager.patch(url, json={"version": 1, "name": "Late"})
    assert stale.status_code == 409
    assert stale.json()["error"] == "stale"
    # moving the plan to a branch the manager does not manage is refused
    hot = node_id(manager, "Hot rolling")
    assert manager.patch(url, json={"version": 2, "owner_org_node_id": hot}).status_code == 403
    assert manager.patch("/api/plans/999999", json={"version": 1}).status_code == 404


def test_only_managers_of_the_owner_edit_or_delete_a_plan(anna: TestClient) -> None:
    digital = plan_id(anna, "Digital plant")
    assert anna.patch(f"/api/plans/{digital}", json={"version": 1, "name": "x"}).status_code == 403
    assert anna.delete(f"/api/plans/{digital}").status_code == 403
    assert anna.delete("/api/plans/999999").status_code == 404


def test_deleting_a_plan_notes_it_in_its_projects_logbooks(
    admin: TestClient, sample_database: Database, sample: Sample
) -> None:
    """[AP-1]"""
    spec = plan_spec(sample, "Safe workplace")
    sample_number = spec.projects[0]
    safe = plan_id(admin, "Safe workplace")
    before = len(log_of(admin, sample_number))
    assert admin.delete(f"/api/plans/{safe}").status_code == 204
    assert not any(p["name"] == "Safe workplace" for p in admin.get("/api/plans").json())
    entry = log_of(admin, sample_number)[0]
    assert (entry["field"], entry["to_value"]) == ("action_plans", "Removed from Safe workplace")
    assert len(log_of(admin, sample_number)) == before + 1
    with sample_database.session() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(ActionPlan).where(ActionPlan.id == safe)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionPlanProject)
                .where(ActionPlanProject.plan_id == safe)
            )
            == 0
        )


# ---------------------------------------------------------------- linking


def test_adding_a_project_to_a_plan_is_logged_in_the_project(
    admin: TestClient, sample: Sample
) -> None:
    digital = plan_id(admin, "Digital plant")
    outside = next(
        p for p in sample.projects
        if "Digital plant" not in p.plans and p.status.value not in {"rejected"}
    )  # fmt: skip
    response = admin.post(f"/api/plans/{digital}/projects", json={"number": outside.number})
    assert response.status_code == 201
    assert response.json()["project_count"] == len(plan_spec(sample, "Digital plant").projects) + 1
    assert log_of(admin, outside.number)[0]["to_value"] == "Added to Digital plant"
    count = len(log_of(admin, outside.number))
    again = admin.post(f"/api/plans/{digital}/projects", json={"number": outside.number})
    assert again.status_code == 201
    assert len(log_of(admin, outside.number)) == count  # idempotent
    removed = admin.delete(f"/api/plans/{digital}/projects/{outside.number}")
    assert removed.json()["project_count"] == len(plan_spec(sample, "Digital plant").projects)
    assert log_of(admin, outside.number)[0]["to_value"] == "Removed from Digital plant"


def test_linking_rights_and_unknown_things(
    anna: TestClient, admin: TestClient, clients: ClientFactory
) -> None:
    digital = plan_id(anna, "Digital plant")
    assert anna.post(f"/api/plans/{digital}/projects", json={"number": 4102}).status_code == 403
    assert (
        clients().post(f"/api/plans/{digital}/projects", json={"number": 4102}).status_code == 401
    )
    assert admin.post(f"/api/plans/{digital}/projects", json={"number": 1}).status_code == 404
    assert admin.post("/api/plans/999999/projects", json={"number": 4102}).status_code == 404
    assert anna.delete(f"/api/plans/{digital}/projects/4102").status_code == 403
    coordinator = clients("tomas.rivera")  # coordinates #4102: project.edit on it is enough
    safe = plan_id(coordinator, "Safe workplace")
    assert coordinator.post(f"/api/plans/{safe}/projects", json={"number": 4102}).status_code == 201


# ---------------------------------------------------------------- overview


def test_the_overview_groups_by_top_level_department_with_the_owner_first(
    anna: TestClient, sample: Sample
) -> None:
    """[AP-5]"""
    spec = plan_spec(sample, "Energy & resources 2027")
    by_number = {p.number: p for p in sample.projects}
    body = anna.get(f"/api/plans/{plan_id(anna, spec.name)}/overview").json()

    groups = {g["name"]: g for g in body["groups"]}
    expected = {top(by_number[n].node) for n in spec.projects}
    assert set(groups) == expected
    assert body["department_count"] == len(expected)
    assert body["project_count"] == len(spec.projects)
    assert body["groups"][0]["name"] == spec.owner_node  # the owner's group first
    assert [g["is_owner"] for g in body["groups"]].count(True) == 1
    assert body["groups"][0]["is_owner"] is True
    rest = [g["name"] for g in body["groups"][1:]]
    assert rest == sorted(rest, key=str.casefold)
    for name, group in groups.items():
        wanted = sorted(
            (n for n in spec.projects if top(by_number[n].node) == name),
            key=lambda n: (by_number[n].start, n),
        )
        assert [p["number"] for p in group["projects"]] == wanted
        counts: dict[str, int] = {}
        for n in wanted:
            counts[by_number[n].status.value] = counts.get(by_number[n].status.value, 0) + 1
        assert group["status_counts"] == counts
        assert group["start_date"] == min(by_number[n].start for n in wanted).isoformat()
        assert group["end_date"] == max(by_number[n].end for n in wanted).isoformat()
    assert body["owner_name"] == spec.owner_node
    assert body["coordinator"]["name"] == spec.coordinator


def test_the_plan_totals_equal_the_sums_computed_here(anna: TestClient, sample: Sample) -> None:
    """[AP-4]"""
    spec = plan_spec(sample, "Digital plant")
    body = anna.get(f"/api/plans/{plan_id(anna, spec.name)}/overview").json()
    by_number = {p.number: p for p in sample.projects}
    planned = sum(float(v) for n in spec.projects for v in by_number[n].planned.values())
    members = set(spec.projects)
    logged = sum(e.minutes for e in sample.entries if e.project in members) / 480
    assert body["days"]["planned"] == pytest.approx(planned)
    assert body["days"]["logged"] == pytest.approx(logged)
    assert 0 <= body["days"]["logged_percent"] <= 100
    group_sum = sum(g["days"]["planned"] for g in body["groups"])
    assert group_sum == pytest.approx(planned)
    for group in body["groups"]:
        for project in group["projects"]:
            own = sum(float(v) for v in by_number[project["number"]].planned.values())
            assert project["days"]["planned"] == pytest.approx(own)


def test_projects_the_viewer_cannot_see_are_left_out_of_rows_totals_and_feed(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    """[AP-8]"""
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))  # nobody is a Viewer by default any more
    tomas = clients("tomas.rivera")
    spec = plan_spec(sample, "Digital plant")
    mine = {
        n
        for n in spec.projects
        if any(p.number == n and "Tomás Rivera" in p.members for p in sample.projects)
    }
    assert mine  # #4102 is in the Digital plant
    plans = tomas.get("/api/plans").json()
    assert plans  # plans themselves stay listed
    digital = next(p for p in plans if p["name"] == "Digital plant")
    assert digital["project_count"] == len(mine)
    body = tomas.get(f"/api/plans/{digital['id']}/overview").json()
    shown = {p["number"] for g in body["groups"] for p in g["projects"]}
    assert shown == mine
    assert body["project_count"] == len(mine)
    feed = tomas.get(f"/api/plans/{digital['id']}/feed").json()
    assert {i["project_number"] for i in feed["items"]} <= mine


# ---------------------------------------------------------------- feed


def test_the_feed_mixes_remarks_and_changes_newest_first_at_most_eight(
    anna: TestClient, sample: Sample
) -> None:
    """[AP-6]"""
    digital = plan_id(anna, "Digital plant")
    items = anna.get(f"/api/plans/{digital}/feed").json()["items"]
    assert 0 < len(items) <= 8
    times = [i["at"] for i in items]
    assert times == sorted(times, reverse=True)
    assert {i["kind"] for i in items} <= {"remark", "log"}
    for item in items:
        if item["kind"] == "remark":
            assert item["tab"] == "remarks"
            assert item["excerpt"]
            assert len(item["excerpt"].splitlines()) <= 3
            assert "**" not in item["excerpt"]
        else:
            assert item["tab"] == "logbook"
            assert item["field"] != "Project"  # creations are not changes
    members = set(plan_spec(sample, "Digital plant").projects)
    assert {i["project_number"] for i in items} <= members


def test_a_projects_feed_is_its_own(anna: TestClient) -> None:
    digital = plan_id(anna, "Digital plant")
    items = anna.get(f"/api/plans/{digital}/feed", params={"project": 4102}).json()["items"]
    assert items
    assert {i["project_number"] for i in items} == {4102}
    first = items[0]
    assert first["kind"] == "remark"  # the design's newest item on #4102 is Sofia's remark
    assert first["actor"]["name"] == "Sofia Lind"
    assert first["excerpt"].startswith("Done:")
    assert anna.get(f"/api/plans/{digital}/feed", params={"project": 1}).status_code == 404
    assert anna.get("/api/plans/999999/feed").status_code == 404
    assert anna.get("/api/plans/999999/overview").status_code == 404


def test_an_empty_plan_has_an_empty_overview_and_feed(
    admin: TestClient,
) -> None:
    created = admin.post(
        "/api/plans",
        json={
            "name": "Nothing yet",
            "owner_org_node_id": node_id(admin, "Quality"),
            "coordinator_id": person_id(admin, "Anna Claes"),
            "hue": 90,
        },
    ).json()
    overview = admin.get(f"/api/plans/{created['id']}/overview").json()
    assert overview["groups"] == []
    assert overview["project_count"] == 0
    assert overview["days"]["planned"] == 0
    assert admin.get(f"/api/plans/{created['id']}/feed").json() == {"items": []}


def test_a_plan_link_is_logged_with_who_made_it(
    admin: TestClient, sample_database: Database
) -> None:
    plan = plan_id(admin, "Line performance 2026")
    admin.post(f"/api/plans/{plan}/projects", json={"number": 4340})
    with sample_database.session() as session:
        entry = session.scalar(
            select(LogEntry)
            .join(Project, Project.id == LogEntry.project_id)
            .where(Project.number == 4340)
            .order_by(LogEntry.id.desc())
        )
        admin_id = session.scalar(select(User.id).where(User.username == "admin"))
    assert entry is not None
    assert entry.to_value == "Added to Line performance 2026"
    assert entry.actor_id == admin_id
