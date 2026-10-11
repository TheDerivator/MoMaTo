"""One project: reading, creating, editing, members, plan links, deleting, the logbook.

Every endpoint has its success and its 401 / 403 / 404 / 409 / 422 cases. [PP-3] [PP-6]
"""

from datetime import date, timedelta
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from momato.db.models import (
    ActionPlanProject,
    LogEntry,
    PlannedDays,
    Post,
    Project,
    ProjectDetail,
    Task,
)
from momato.db.session import Database
from momato.domain.access import Scope
from momato.domain.calendar import Quarter
from momato.services.sample_data import Sample
from tests.api.conftest import ClientFactory, grant

TODAY = date(2026, 10, 8)


def bootstrap(client: TestClient) -> dict[str, Any]:
    return client.get("/api/bootstrap").json()


def person_id(client: TestClient, name: str) -> int:
    return next(p["id"] for p in bootstrap(client)["people"] if p["name"] == name)


def node_id(client: TestClient, name: str) -> int:
    return next(n["id"] for n in bootstrap(client)["org"] if n["name"] == name)


def plan_id(client: TestClient, name: str) -> int:
    return next(p["id"] for p in bootstrap(client)["plans"] if p["name"] == name)


def edit(client: TestClient, number: int, **fields: Any) -> Any:
    version = client.get(f"/api/projects/{number}").json()["version"]
    return client.patch(f"/api/projects/{number}", json={"version": version, **fields})


# ---------------------------------------------------------------- reading


def test_a_project_has_everything_the_page_needs(anna: TestClient, sample: Sample) -> None:
    body = anna.get("/api/projects/4102").json()
    assert body["name"] == "Sensor retrofit on conveyor 4"
    assert body["status"] == "progress"
    assert body["org_node_name"] == "Level 1-2 automation"
    assert body["coordinator"]["name"] == "Tomás Rivera"
    assert body["members"][0]["name"] == "Tomás Rivera"  # the coordinator first
    spec = next(p for p in sample.projects if p.number == 4102)
    assert {m["name"] for m in body["members"]} == set(spec.members)
    assert body["timeline_text"] == "66% of the timeline behind us"
    assert [t["name"] for t in body["tasks"]][:2] == ["Study & scoping", "Supplier offers"]
    assert body["remark_count"] == 4
    assert body["log_count"] == 7
    assert body["version"] == 1
    assert (body["can_edit"], body["can_comment"], body["can_delete"]) == (False, True, False)
    assert body["priority"] == "high"
    assert set(body["details"]) <= {
        "erp_order", "original_project", "activity_type", "sponsor", "budget_owner",
        "steering_committee", "strategic_axis", "process", "programme", "tags",
        "ease_of_execution", "operations_maintenance", "procurement", "engineering",
        "planning_phase",
    }  # fmt: skip


def test_days_planned_logged_and_expected_equal_values_computed_here(
    anna: TestClient, sample: Sample
) -> None:
    """[R4.4] Computed day by day from the specs, not with the application's functions."""
    spec = next(p for p in sample.projects if p.number == 4102)
    planned = sum((Fraction(str(v)) for v in spec.planned.values()), Fraction(0))
    logged_minutes = sum(e.minutes for e in sample.entries if e.project == 4102)
    expected = Fraction(0)
    for (_, quarter_start), days in spec.planned.items():
        quarter = Quarter.starting(quarter_start)
        weekdays = [
            quarter.start + timedelta(n)
            for n in range((quarter.end - quarter.start).days + 1)
            if (quarter.start + timedelta(n)).weekday() < 5
        ]
        if quarter.end < TODAY:
            expected += Fraction(str(days))
        elif quarter.start <= TODAY:
            elapsed = sum(1 for d in weekdays if d <= TODAY)
            expected += Fraction(str(days)) * elapsed / len(weekdays)
    days = anna.get("/api/projects/4102").json()["days"]
    assert days["planned"] == pytest.approx(float(planned))
    assert days["logged"] == pytest.approx(logged_minutes / 480)
    assert days["expected"] == pytest.approx(float(expected))
    assert days["logged_percent"] == pytest.approx(
        min(100.0, logged_minutes / 480 / float(planned) * 100)
    )
    assert days["expected_percent"] == pytest.approx(float(expected / planned * 100))


def test_an_unknown_project_is_404(anna: TestClient) -> None:
    response = anna.get("/api/projects/1")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_a_visitor_cannot_read_a_project(clients: ClientFactory) -> None:
    assert clients().get("/api/projects/4102").status_code == 401


# ---------------------------------------------------------------- creating


def new_project(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "  A brand new project  ",
        "start_date": "2026-11-02",
        "end_date": "2027-02-26",
    }
    body.update(overrides)
    return body


def test_creating_a_project_assigns_the_next_number_and_logs_it(
    admin: TestClient, sample: Sample
) -> None:
    """[PL-8] [PG-6] D-017"""
    body = new_project(
        org_node_id=node_id(admin, "Quality"),
        coordinator_id=person_id(admin, "Anna Claes"),
        goal="Make it good.",
        priority="high",
        status="preparation",
        use_template=True,
    )
    response = admin.post("/api/projects", json=body)
    assert response.status_code == 201
    created = response.json()
    assert created["number"] == max(p.number for p in sample.projects) + 1  # 4341
    assert created["name"] == "A brand new project"
    assert (created["status"], created["priority"], created["goal"]) == (
        "preparation",
        "high",
        "Make it good.",
    )
    assert [m["name"] for m in created["members"]] == ["Anna Claes"]
    assert created["tasks"][0]["name"] == "Study & scoping"
    assert len(created["tasks"]) == 6
    assert created["tasks"][0]["planned_start"] == "2026-11-02"
    assert created["tasks"][-1]["planned_end"] == "2027-02-26"
    log = admin.get(f"/api/projects/{created['number']}/log").json()
    assert [(e["field"], e["to_value"]) for e in log["items"]] == [("created", "Created")]

    second = admin.post(
        "/api/projects",
        json=new_project(
            org_node_id=node_id(admin, "Quality"), coordinator_id=person_id(admin, "Anna Claes")
        ),
    )
    assert second.json()["number"] == created["number"] + 1
    assert second.json()["tasks"] == []  # no template asked for
    assert second.json()["status"] == "idea"  # the default


def test_the_caller_is_the_default_coordinator(
    clients: ClientFactory, sample_database: Database
) -> None:
    grant(sample_database, "anna.claes", "project_admin", Scope.everywhere())
    anna = clients("anna.claes")
    created = anna.post("/api/projects", json=new_project(org_node_id=node_id(anna, "Quality")))
    assert created.status_code == 201
    assert created.json()["coordinator"]["name"] == "Anna Claes"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"end_date": "2026-10-01"}, "end date"),
        ({"org_node_id": 999_999}, "no org node"),
        ({"coordinator_id": 999_999}, "no such coordinator"),
        ({"coordinator_id": None}, "choose a coordinator"),  # an administrator has no person
    ],
)
def test_creating_with_invalid_input_is_422(
    admin: TestClient, override: dict[str, Any], message: str
) -> None:
    body = new_project(
        org_node_id=node_id(admin, "Quality"), coordinator_id=person_id(admin, "Anna Claes")
    )
    body.update(override)
    response = admin.post("/api/projects", json=body)
    assert response.status_code == 422
    assert message in response.json()["message"]


def test_a_blank_name_or_missing_fields_are_422(admin: TestClient) -> None:
    assert (
        admin.post("/api/projects", json=new_project(name="   ", org_node_id=1)).status_code == 422
    )
    assert admin.post("/api/projects", json={"name": "x"}).status_code == 422


def test_creating_needs_edit_rights_in_the_branch(
    clients: ClientFactory, sample_database: Database
) -> None:
    viewer = clients("anna.claes")
    quality = node_id(viewer, "Quality")
    assert viewer.post("/api/projects", json=new_project(org_node_id=quality)).status_code == 403
    assert clients().post("/api/projects", json=new_project(org_node_id=quality)).status_code == 401
    grant(sample_database, "anna.claes", "project_admin", Scope.node(quality))
    allowed = clients("anna.claes")
    assert allowed.post("/api/projects", json=new_project(org_node_id=quality)).status_code == 201
    elsewhere = node_id(allowed, "Hot rolling")
    assert allowed.post("/api/projects", json=new_project(org_node_id=elsewhere)).status_code == 403


# ---------------------------------------------------------------- editing core fields


def log_of(client: TestClient, number: int) -> list[dict[str, Any]]:
    return client.get(f"/api/projects/{number}/log").json()["items"]


@pytest.mark.parametrize(
    ("field", "value", "log_field", "old", "new"),
    [
        ("name", "Renamed sensor retrofit", "title", "Sensor retrofit on conveyor 4", "Renamed sensor retrofit"),
        ("status", "hold", "status", "In progress", "On hold"),
        ("start_date", "2025-12-01", "start_date", "3 Nov 2025", "1 Dec 2025"),
        ("end_date", "2027-06-30", "end_date", "31 Mar 2027", "30 Jun 2027"),
        ("priority", "low", "priority", "High", "Low"),
        ("goal", "A shorter goal.", "goal", "Replace the end-of-life sensors on conveyor 4 with networked ones, so belt speed, load and temperature are visible live and stops can be predicted instead of discovered.", "A shorter goal."),
    ],
)  # fmt: skip
def test_changing_a_core_field_writes_exactly_one_logbook_entry(
    admin: TestClient, field: str, value: str, log_field: str, old: str, new: str
) -> None:
    """[LB-1]"""
    before = log_of(admin, 4102)
    response = edit(admin, 4102, **{field: value})
    assert response.status_code == 200
    assert response.json()["version"] == 2
    after = log_of(admin, 4102)
    assert len(after) == len(before) + 1
    entry = after[0]  # newest first
    assert (entry["field"], entry["from_value"], entry["to_value"]) == (log_field, old, new)
    assert entry["actor"]["name"] == "Administrator"


def test_changing_the_coordinator_and_the_org_node_each_log_once(admin: TestClient) -> None:
    """[OV-4]"""
    sofia = person_id(admin, "Sofia Lind")
    response = edit(admin, 4102, coordinator_id=sofia)
    assert response.status_code == 200
    entry = log_of(admin, 4102)[0]
    assert (entry["field"], entry["from_value"], entry["to_value"]) == (
        "coordinator", "Tomás Rivera", "Sofia Lind",
    )  # fmt: skip
    assert response.json()["coordinator"]["name"] == "Sofia Lind"

    count = len(log_of(admin, 4102))
    moved = edit(admin, 4102, org_node_id=node_id(admin, "Data & analytics"))
    assert moved.status_code == 200
    after = log_of(admin, 4102)
    assert len(after) == count + 1
    assert (after[0]["field"], after[0]["from_value"], after[0]["to_value"]) == (
        "org_node", "Level 1-2 automation", "Data & analytics",
    )  # fmt: skip


def test_a_new_coordinator_who_is_not_a_member_becomes_one_and_that_is_logged(
    admin: TestClient,
) -> None:
    pieter = person_id(admin, "Hilde Casteels")
    response = edit(admin, 4102, coordinator_id=pieter)
    assert response.status_code == 200
    assert "Hilde Casteels" in [m["name"] for m in response.json()["members"]]
    fields = [(e["field"], e["to_value"]) for e in log_of(admin, 4102)[:2]]
    assert sorted(fields) == [("coordinator", "Hilde Casteels"), ("people", "Added Hilde Casteels")]


def test_changing_several_fields_at_once_logs_each(admin: TestClient) -> None:
    before = len(log_of(admin, 4102))
    response = edit(admin, 4102, name="Both at once", priority="medium", status="finished")
    assert response.status_code == 200
    assert response.json()["version"] == 2  # one edit, one version
    assert len(log_of(admin, 4102)) == before + 3


def test_an_unchanged_or_empty_edit_changes_nothing(admin: TestClient) -> None:
    """[PP-3]"""
    before = admin.get("/api/projects/4102").json()
    log_count = len(log_of(admin, 4102))
    same = edit(
        admin, 4102, name=before["name"], status=before["status"], priority=before["priority"]
    )
    assert same.status_code == 200
    assert same.json()["version"] == before["version"]
    assert len(log_of(admin, 4102)) == log_count
    assert edit(admin, 4102).json()["version"] == before["version"]  # nothing sent
    assert edit(admin, 4102, name="   ").status_code == 422  # a title cannot be emptied


def test_a_stale_edit_is_refused_with_409(admin: TestClient, clients: ClientFactory) -> None:
    """[PP-6] Two editors: the second saves with the version they loaded."""
    version = admin.get("/api/projects/4102").json()["version"]
    assert (
        admin.patch("/api/projects/4102", json={"version": version, "priority": "low"}).status_code
        == 200
    )
    stale = admin.patch("/api/projects/4102", json={"version": version, "goal": "Late"})
    assert stale.status_code == 409
    assert stale.json()["error"] == "stale"
    assert "Someone else changed this project" in stale.json()["message"]
    assert admin.get("/api/projects/4102").json()["goal"].startswith("Replace")  # nothing applied


def test_date_rules_are_422(admin: TestClient) -> None:
    assert edit(admin, 4102, end_date="2025-01-01").status_code == 422
    assert edit(admin, 4102, start_date="2028-01-01").status_code == 422  # after the current end
    assert edit(admin, 4102, status="nonsense").status_code == 422
    assert edit(admin, 4102, org_node_id=999_999).status_code == 422
    assert edit(admin, 4102, coordinator_id=999_999).status_code == 422


def test_editing_needs_the_right_and_an_existing_project(
    clients: ClientFactory, anna: TestClient, sample_database: Database
) -> None:
    assert edit(anna, 4102, priority="low").status_code == 403  # a viewer
    assert clients().patch("/api/projects/4102", json={"version": 1}).status_code == 401
    assert anna.patch("/api/projects/1", json={"version": 1}).status_code == 404
    # A member (Anna is on #4102) may comment but not edit; the coordinator may edit.
    tomas = clients("tomas.rivera")
    assert edit(tomas, 4102, priority="low").status_code == 200
    assert edit(tomas, 4120, priority="low").status_code == 403  # not theirs


def test_a_coordinator_without_any_role_edits_their_project_and_no_other(
    clients: ClientFactory, sample: Sample
) -> None:
    person = "Tomás Rivera"
    tomas = clients("tomas.rivera")
    own = [p.number for p in sample.projects if p.coordinator == person]
    other = next(
        p.number for p in sample.projects if p.coordinator != person and person not in p.members
    )
    assert own
    assert all(edit(tomas, n, priority="low").status_code == 200 for n in own[:3])
    assert edit(tomas, other, priority="low").status_code == 403


def test_a_project_administrator_on_one_department_edits_its_projects_only(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    stl = project_node_by_name(sample_database, "STL")
    grant(sample_database, "bram.peeters", "project_admin", Scope.node(stl))
    bram = clients("bram.peeters")
    in_stl = next(
        p.number
        for p in sample.projects
        if p.node.split("/")[0] == "STL" and p.coordinator != "Bram Peeters"
    )
    elsewhere = next(
        p.number
        for p in sample.projects
        if p.node.split("/")[0] == "Hot rolling" and "Bram Peeters" not in p.members
    )
    assert edit(bram, in_stl, priority="low").status_code == 200
    assert edit(bram, elsewhere, priority="low").status_code == 403
    # Moving a project out of the branch needs edit rights on the new branch as well.
    hot = project_node_by_name(sample_database, "Hot rolling")
    assert edit(bram, in_stl, org_node_id=hot).status_code == 403


def project_node_by_name(database: Database, name: str) -> int:
    from momato.db.models import OrgNode

    with database.session() as session:
        found = session.scalar(select(OrgNode.id).where(OrgNode.name == name))
        assert found is not None
        return found


# ---------------------------------------------------------------- details


def test_changing_a_detail_field_writes_no_logbook_entry(
    admin: TestClient, sample_database: Database
) -> None:
    """[DT-3] D-016: detail changes are not logged for now."""
    before = len(log_of(admin, 4102))
    response = edit(
        admin, 4102, details={"erp_order": "EO-9999-4102", "tags": ["quick win", "data"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["details"]["erp_order"] == "EO-9999-4102"
    assert body["details"]["tags"] == ["quick win", "data"]
    assert body["version"] == 2
    assert len(log_of(admin, 4102)) == before
    with sample_database.session() as session:
        stored = session.scalar(
            select(ProjectDetail.value)
            .where(ProjectDetail.field_key == "erp_order")
            .join(Project, Project.id == ProjectDetail.project_id)
            .where(Project.number == 4102)
        )
    assert stored == '"EO-9999-4102"'


def test_a_detail_can_be_cleared_and_unchanged_values_do_not_bump_the_version(
    admin: TestClient,
) -> None:
    edit(admin, 4102, details={"erp_order": "EO-1"})
    again = edit(admin, 4102, details={"erp_order": "EO-1"})
    assert again.json()["version"] == 2  # same value: nothing changed
    cleared = edit(admin, 4102, details={"erp_order": None})
    assert "erp_order" not in cleared.json()["details"]


@pytest.mark.parametrize(
    ("details", "message"),
    [
        ({"no_such_field": "x"}, "unknown detail field"),
        ({"activity_type": "Not a choice"}, "must be one of"),
        ({"engineering": "yes"}, "yes or no"),
        ({"sponsor": 999_999}, "no such person"),
        ({"original_project": 1}, "no project #1"),
        ({"tags": "not a list"}, "list of text"),
        ({"erp_order": 5}, "must be text"),
    ],
)
def test_invalid_detail_values_are_422(
    admin: TestClient, details: dict[str, Any], message: str
) -> None:
    response = edit(admin, 4102, details=details)
    assert response.status_code == 422
    assert message in response.json()["message"]


def test_detail_values_of_every_type_round_trip(admin: TestClient) -> None:
    sofia = person_id(admin, "Sofia Lind")
    values = {
        "erp_order": "EO-77",
        "original_project": 3876,
        "activity_type": "Study",
        "sponsor": sofia,
        "tags": ["a", "b"],
        "engineering": True,
        "operations_maintenance": False,
        "planning_phase": "Close-out",
    }
    body = edit(admin, 4102, details=values).json()
    for key, value in values.items():
        assert body["details"][key] == value


# ---------------------------------------------------------------- members


def test_adding_and_removing_members_are_logged(admin: TestClient) -> None:
    """[PD-4]"""
    hilde = person_id(admin, "Hilde Casteels")
    response = admin.post("/api/projects/4102/members", json={"user_id": hilde})
    assert response.status_code == 201
    assert "Hilde Casteels" in [m["name"] for m in response.json()["members"]]
    assert log_of(admin, 4102)[0]["to_value"] == "Added Hilde Casteels"

    count = len(log_of(admin, 4102))
    again = admin.post("/api/projects/4102/members", json={"user_id": hilde})
    assert again.status_code == 201  # a set operation: nothing changes
    assert len(log_of(admin, 4102)) == count

    removed = admin.delete(f"/api/projects/4102/members/{hilde}")
    assert removed.status_code == 200
    assert "Hilde Casteels" not in [m["name"] for m in removed.json()["members"]]
    assert log_of(admin, 4102)[0]["to_value"] == "Removed Hilde Casteels"


def test_removing_a_member_removes_their_planned_days_but_not_their_booked_time(
    admin: TestClient, sample_database: Database, sample: Sample
) -> None:
    spec = next(p for p in sample.projects if p.number == 4102)
    sofia = person_id(admin, "Sofia Lind")
    with sample_database.session() as session:
        before = session.scalar(
            select(func.count()).select_from(PlannedDays).where(PlannedDays.user_id == sofia)
        )
    assert admin.delete(f"/api/projects/4102/members/{sofia}").status_code == 200
    with sample_database.session() as session:
        project_id = session.scalar(select(Project.id).where(Project.number == 4102))
        left = session.scalar(
            select(func.count())
            .select_from(PlannedDays)
            .where(PlannedDays.project_id == project_id, PlannedDays.user_id == sofia)
        )
        elsewhere = session.scalar(
            select(func.count())
            .select_from(PlannedDays)
            .where(PlannedDays.project_id != project_id, PlannedDays.user_id == sofia)
        )
    assert left == 0
    assert before is not None
    assert elsewhere == before - sum(1 for (p, _) in spec.planned if p == "Sofia Lind")
    grid = admin.get("/api/projects/4102/planned-days").json()
    assert "Sofia Lind" not in [r["person"]["name"] for r in grid["rows"]]
    booked = any(e.person == "Sofia Lind" and e.project == 4102 for e in sample.entries)
    assert booked == ("Sofia Lind" in [r["person"]["name"] for r in grid["also_booked"]])


def test_member_rules(admin: TestClient, anna: TestClient, clients: ClientFactory) -> None:
    coordinator = person_id(admin, "Tomás Rivera")
    refused = admin.delete(f"/api/projects/4102/members/{coordinator}")
    assert refused.status_code == 422
    assert "change the coordinator first" in refused.json()["message"]
    hilde = person_id(admin, "Hilde Casteels")
    assert admin.delete(f"/api/projects/4102/members/{hilde}").status_code == 404  # not a member
    assert admin.post("/api/projects/4102/members", json={"user_id": 999_999}).status_code == 422
    assert (
        admin.post("/api/projects/4102/members", json={"user_id": 1}).status_code == 422
    )  # system
    assert anna.post("/api/projects/4102/members", json={"user_id": hilde}).status_code == 403
    assert clients().post("/api/projects/4102/members", json={"user_id": hilde}).status_code == 401


# ---------------------------------------------------------------- action plans


def test_linking_and_unlinking_an_action_plan_is_logged(admin: TestClient) -> None:
    """[AP-7]"""
    safe = plan_id(admin, "Safe workplace")
    response = admin.put(f"/api/projects/4102/plans/{safe}")
    assert response.status_code == 200
    assert safe in response.json()["plan_ids"]
    assert log_of(admin, 4102)[0]["to_value"] == "Added to Safe workplace"

    count = len(log_of(admin, 4102))
    assert admin.put(f"/api/projects/4102/plans/{safe}").status_code == 200  # idempotent
    assert len(log_of(admin, 4102)) == count

    removed = admin.delete(f"/api/projects/4102/plans/{safe}")
    assert safe not in removed.json()["plan_ids"]
    assert log_of(admin, 4102)[0]["to_value"] == "Removed from Safe workplace"


def test_linking_needs_project_edit_or_plan_manage_on_the_owner(
    clients: ClientFactory, sample_database: Database
) -> None:
    """D-031"""
    safe_owner = project_node_by_name(sample_database, "Safety & environment")
    viewer = clients("anna.claes")
    safe = plan_id(viewer, "Safe workplace")
    assert viewer.put(f"/api/projects/4102/plans/{safe}").status_code == 403
    grant(sample_database, "anna.claes", "project_admin", Scope.node(safe_owner))
    manager = clients("anna.claes")  # plan.manage on the plan's owner, nothing on the project
    assert manager.put(f"/api/projects/4102/plans/{safe}").status_code == 200
    assert manager.delete(f"/api/projects/4102/plans/{safe}").status_code == 200
    assert manager.put("/api/projects/4102/plans/999999").status_code == 404
    assert clients().put(f"/api/projects/4102/plans/{safe}").status_code == 401


# ---------------------------------------------------------------- delete


def test_a_project_with_booked_time_cannot_be_deleted(admin: TestClient) -> None:
    """[ADM-7] D-018"""
    response = admin.delete("/api/projects/4102")
    assert response.status_code == 409
    assert "time is booked" in response.json()["message"]
    assert admin.get("/api/projects/4102").status_code == 200


def test_deleting_a_project_removes_what_hangs_on_it(
    admin: TestClient, sample_database: Database, sample: Sample
) -> None:
    """[ADM-7]"""
    booked = {e.project for e in sample.entries}
    candidate = next(
        p for p in sample.projects if p.number not in booked and p.remarks and p.plans and p.planned
    )
    number = candidate.number
    with sample_database.session() as session:
        project_id = session.scalar(select(Project.id).where(Project.number == number))
    assert admin.delete(f"/api/projects/{number}").status_code == 204
    assert admin.get(f"/api/projects/{number}").status_code == 404
    with sample_database.session() as session:
        for model in (Task, LogEntry, PlannedDays, ProjectDetail, Post, ActionPlanProject):
            count = session.scalar(
                select(func.count()).select_from(model).where(model.project_id == project_id)
            )
            assert count == 0, model.__name__
    page = admin.get("/api/projects", params={"limit": 100}).json()
    assert number not in [r["number"] for r in page["items"]]


def test_deleting_needs_the_delete_right(
    clients: ClientFactory, anna: TestClient, sample: Sample
) -> None:
    booked = {e.project for e in sample.entries}
    free = next(p.number for p in sample.projects if p.number not in booked)
    tomas_project = (
        next(
            p.number
            for p in sample.projects
            if p.coordinator == "Tomás Rivera" and p.number not in booked
        )
        if any(p.coordinator == "Tomás Rivera" and p.number not in booked for p in sample.projects)
        else free
    )
    assert anna.delete(f"/api/projects/{free}").status_code == 403
    assert clients().delete(f"/api/projects/{free}").status_code == 401
    coordinator = clients("tomas.rivera")  # coordinators edit, they do not delete
    assert coordinator.delete(f"/api/projects/{tomas_project}").status_code == 403
    assert anna.delete("/api/projects/1").status_code == 404


# ---------------------------------------------------------------- logbook


def test_the_logbook_of_4102_is_the_designs(admin: TestClient) -> None:
    """[LB-1] [LB-3]"""
    page = admin.get("/api/projects/4102/log").json()
    assert page["count"] == page["total"] == 7
    newest = page["items"][0]
    assert (newest["field"], newest["field_label"]) == ("end_date", "End date")
    assert (newest["from_value"], newest["to_value"]) == ("29 Jan 2027", "31 Mar 2027")
    assert newest["hue"] == 60
    assert newest["actor"]["name"] == "Tomás Rivera"
    oldest = page["items"][-1]
    assert (oldest["field"], oldest["to_value"], oldest["hue"]) == ("created", "Created", 90)
    times = [e["at"] for e in page["items"]]
    assert times == sorted(times, reverse=True)


@pytest.mark.parametrize(
    ("group", "fields"),
    [
        ("title", {"title"}),
        ("status", {"status"}),
        ("dates", {"end_date"}),
        ("people", {"people", "coordinator"}),
        ("plans", set()),
        ("all", {"created", "status", "people", "coordinator", "title", "end_date"}),
    ],
)
def test_the_logbook_filter_chips(admin: TestClient, group: str, fields: set[str]) -> None:
    """[LB-2]"""
    page = admin.get("/api/projects/4102/log", params={"filter": group}).json()
    assert {e["field"] for e in page["items"]} == fields
    assert page["count"] == 7  # the tab's count is the full count
    assert page["total"] == len(page["items"])


def test_the_logbook_needs_a_known_filter_and_a_visible_project(
    admin: TestClient, clients: ClientFactory
) -> None:
    assert admin.get("/api/projects/4102/log", params={"filter": "nonsense"}).status_code == 422
    assert admin.get("/api/projects/1/log").status_code == 404
    assert clients().get("/api/projects/4102/log").status_code == 401
