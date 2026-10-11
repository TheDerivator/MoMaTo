"""Tasks (the gantt rows) and People & days (planned days per member and quarter).

[PG-4] [PG-5] [PG-6] [PD-3] [PD-4] [PD-5] D-032
"""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from momato.db.models import Project, TimeEntry, User
from momato.db.session import Database
from momato.domain.calendar import Quarter
from momato.services.sample_data import Sample
from tests.api.conftest import ClientFactory
from tests.api.test_projects import person_id

TODAY = date(2026, 10, 8)


def tasks(client: TestClient, number: int = 4102) -> list[dict[str, Any]]:
    return client.get(f"/api/projects/{number}/tasks").json()


def task_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Training of operators",
        "planned_start": "2026-11-02",
        "planned_end": "2026-12-11",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------- reading


def test_tasks_come_in_order_with_their_derived_status(anna: TestClient) -> None:
    """[R4.6] On 8 October 2026 #4102 is done up to Order & delivery, then Installation runs."""
    rows = tasks(anna)
    assert [t["name"] for t in rows] == [
        "Study & scoping",
        "Supplier offers",
        "Order & delivery",
        "Installation",
        "Commissioning",
        "Handover & close-out",
    ]
    assert [t["position"] for t in rows] == list(range(6))
    assert [t["status"] for t in rows][:3] == ["done", "done", "done"]
    installation = rows[3]
    assert installation["status"] == "running"
    assert installation["status_text"].endswith("% · running")
    assert rows[4]["status"] == "planned"
    assert rows[4]["status_text"] == "Planned"
    assert [t["is_milestone"] for t in rows] == [False, False, True, False, True, False]
    assert all(t["effective_end"] >= t["planned_end"] for t in rows)


def test_a_slipped_task_shows_its_revised_end(anna: TestClient) -> None:
    installation = tasks(anna)[3]
    assert installation["slipped"] is True
    assert installation["revised_end"] > installation["planned_end"]
    assert installation["effective_end"] == installation["revised_end"]


def test_tasks_of_an_invisible_project_are_404(anna: TestClient, clients: ClientFactory) -> None:
    assert anna.get("/api/projects/1/tasks").status_code == 404
    assert clients().get("/api/projects/4102/tasks").status_code == 401


# ---------------------------------------------------------------- create, edit, move


def test_adding_a_task_puts_it_last(admin: TestClient) -> None:
    created = admin.post("/api/projects/4102/tasks", json=task_body(progress=100))
    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["position"], body["version"]) == ("Training of operators", 6, 1)
    assert body["status"] == "done"  # progress 100 makes a task done (D-008)
    assert [t["name"] for t in tasks(admin)][-1] == "Training of operators"


def test_the_first_task_of_a_project_gets_position_zero(admin: TestClient) -> None:
    created = admin.post(
        "/api/projects",
        json={
            "name": "Empty",
            "org_node_id": next(
                n["id"] for n in admin.get("/api/bootstrap").json()["org"] if n["name"] == "Quality"
            ),
            "coordinator_id": person_id(admin, "Anna Claes"),
            "start_date": "2026-11-02",
            "end_date": "2027-02-26",
        },
    ).json()
    first = admin.post(f"/api/projects/{created['number']}/tasks", json=task_body())
    assert first.json()["position"] == 0
    second = admin.post(f"/api/projects/{created['number']}/tasks", json=task_body(name="Next"))
    assert second.json()["position"] == 1


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"planned_end": "2026-10-01"}, "before its start"),
        ({"revised_end": "2026-12-11"}, "after the planned end"),
        ({"revised_end": "2026-12-01"}, "after the planned end"),
    ],
)
def test_task_dates_are_validated(
    admin: TestClient, override: dict[str, Any], message: str
) -> None:
    """[PG-5]"""
    response = admin.post("/api/projects/4102/tasks", json=task_body(**override))
    assert response.status_code == 422
    assert message in response.json()["message"]
    assert admin.post("/api/projects/4102/tasks", json=task_body(progress=101)).status_code == 422
    assert admin.post("/api/projects/4102/tasks", json=task_body(name="")).status_code == 422


def test_editing_a_task_changes_only_what_was_sent_and_bumps_its_version(admin: TestClient) -> None:
    task = tasks(admin)[4]
    response = admin.patch(
        f"/api/projects/4102/tasks/{task['id']}",
        json={"version": task["version"], "progress": 100, "name": "Commissioned"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["progress"], body["name"], body["version"]) == (100, "Commissioned", 2)
    assert body["status"] == "done"  # a new task at 100 % turns Done
    assert body["planned_start"] == task["planned_start"]
    assert body["planned_end"] == task["planned_end"]


def test_a_revised_end_draws_slippage_and_can_be_cleared(admin: TestClient) -> None:
    task = tasks(admin)[5]
    revised = admin.patch(
        f"/api/projects/4102/tasks/{task['id']}",
        json={"version": task["version"], "revised_end": "2027-09-30"},
    ).json()
    assert revised["slipped"] is True
    cleared = admin.patch(
        f"/api/projects/4102/tasks/{task['id']}",
        json={"version": revised["version"], "clear_revised_end": True},
    ).json()
    assert cleared["revised_end"] is None
    assert cleared["slipped"] is False


def test_a_stale_task_edit_is_409(admin: TestClient) -> None:
    task = tasks(admin)[0]
    url = f"/api/projects/4102/tasks/{task['id']}"
    assert admin.patch(url, json={"version": task["version"], "progress": 50}).status_code == 200
    stale = admin.patch(url, json={"version": task["version"], "progress": 60})
    assert stale.status_code == 409
    assert stale.json()["error"] == "stale"


def test_a_task_of_another_project_is_404(admin: TestClient) -> None:
    other = tasks(admin, 4120)[0]
    assert (
        admin.patch(
            f"/api/projects/4102/tasks/{other['id']}", json={"version": 1, "progress": 5}
        ).status_code
        == 404
    )
    assert admin.delete(f"/api/projects/4102/tasks/{other['id']}").status_code == 404
    assert (
        admin.post(
            f"/api/projects/4102/tasks/{other['id']}/move", json={"direction": "up"}
        ).status_code
        == 404
    )


def test_tasks_move_up_and_down_and_stop_at_the_ends(admin: TestClient) -> None:
    names = [t["name"] for t in tasks(admin)]
    second = tasks(admin)[1]
    moved = admin.post(f"/api/projects/4102/tasks/{second['id']}/move", json={"direction": "up"})
    assert moved.status_code == 200
    after = [t["name"] for t in moved.json()]
    assert after[:2] == [names[1], names[0]]
    assert after[2:] == names[2:]
    assert [t["position"] for t in moved.json()] == list(range(6))

    top = moved.json()[0]
    still = admin.post(f"/api/projects/4102/tasks/{top['id']}/move", json={"direction": "up"})
    assert [t["name"] for t in still.json()] == after  # nothing above the first
    last = moved.json()[-1]
    end = admin.post(f"/api/projects/4102/tasks/{last['id']}/move", json={"direction": "down"})
    assert [t["name"] for t in end.json()] == after
    assert (
        admin.post(
            f"/api/projects/4102/tasks/{top['id']}/move", json={"direction": "sideways"}
        ).status_code
        == 422
    )


def test_editing_tasks_needs_edit_rights(anna: TestClient, clients: ClientFactory) -> None:
    task = tasks(anna)[0]
    assert anna.post("/api/projects/4102/tasks", json=task_body()).status_code == 403
    assert (
        anna.patch(
            f"/api/projects/4102/tasks/{task['id']}", json={"version": 1, "progress": 3}
        ).status_code
        == 403
    )
    assert anna.delete(f"/api/projects/4102/tasks/{task['id']}").status_code == 403
    assert clients().post("/api/projects/4102/tasks", json=task_body()).status_code == 401
    coordinator = clients("tomas.rivera")
    assert coordinator.post("/api/projects/4102/tasks", json=task_body()).status_code == 201


# ---------------------------------------------------------------- delete


def booked_by_task(database: Database, number: int) -> dict[int | None, int]:
    with database.session() as session:
        project_id = session.scalar(select(Project.id).where(Project.number == number))
        rows = session.execute(
            select(TimeEntry.task_id, func.sum(TimeEntry.minutes))
            .where(TimeEntry.project_id == project_id)
            .group_by(TimeEntry.task_id)
        ).all()
    return {task_id: int(minutes) for task_id, minutes in rows}


def test_deleting_a_task_moves_its_hours_to_general(
    admin: TestClient, sample_database: Database, sample: Sample
) -> None:
    """D-032"""
    spec = next(p for p in sample.projects if p.number == 4102)
    by_index: dict[int | None, int] = {}
    for entry in sample.entries:
        if entry.project == 4102:
            by_index[entry.task] = by_index.get(entry.task, 0) + entry.minutes
    victim_index = max((i for i in by_index if i is not None), key=lambda i: by_index[i])
    victim = tasks(admin)[victim_index]
    assert victim["booked_minutes"] == by_index[victim_index]  # the page can ask first

    total_before = sum(booked_by_task(sample_database, 4102).values())
    response = admin.delete(f"/api/projects/4102/tasks/{victim['id']}")
    assert response.status_code == 200
    assert response.json() == {"moved_minutes": by_index[victim_index]}
    after = booked_by_task(sample_database, 4102)
    assert sum(after.values()) == total_before  # nothing lost
    assert victim["id"] not in after
    assert after[None] == by_index.get(None, 0) + by_index[victim_index]
    assert len(tasks(admin)) == len(spec.tasks) - 1


def test_deleting_a_task_without_hours_moves_nothing(admin: TestClient) -> None:
    created = admin.post("/api/projects/4102/tasks", json=task_body()).json()
    assert admin.delete(f"/api/projects/4102/tasks/{created['id']}").json() == {"moved_minutes": 0}


# ---------------------------------------------------------------- people & days


def test_the_grid_has_members_quarters_totals_and_non_member_bookings(
    anna: TestClient, sample: Sample
) -> None:
    grid = anna.get("/api/projects/4102/planned-days").json()
    spec = next(p for p in sample.projects if p.number == 4102)
    assert grid["hours_per_day"] == 8
    assert grid["rows"][0]["person"]["name"] == "Tomás Rivera"
    assert {r["person"]["name"] for r in grid["rows"]} == set(spec.members)
    assert grid["rows"][0]["is_coordinator"] is True
    quarters = grid["quarters"]
    assert quarters == sorted(quarters)
    assert "2026-10-01" in quarters
    assert grid["workdays"] == [Quarter.starting(date.fromisoformat(q)).workdays for q in quarters]
    assert grid["workdays"][quarters.index("2026-10-01")] == 66

    expected_total = sum(float(v) for v in spec.planned.values())
    assert grid["total_planned"] == pytest.approx(expected_total)
    for row in grid["rows"]:
        planned_by_person = sum(
            float(v) for (p, _), v in spec.planned.items() if p == row["person"]["name"]
        )
        assert row["planned_total"] == pytest.approx(planned_by_person)
        assert [c["quarter_start"] for c in row["cells"]] == quarters
    q4 = quarters.index("2026-10-01")
    upcoming = [c["upcoming"] for c in grid["rows"][0]["cells"]]
    assert upcoming[q4] is False  # the current quarter is not upcoming
    assert upcoming[q4 + 1] is True
    logged = sum(e.minutes for e in sample.entries if e.project == 4102) / 480
    assert grid["total_logged"] == pytest.approx(logged)


def test_a_cell_is_set_in_half_days_and_cleared_with_zero(admin: TestClient) -> None:
    """[PD-3]"""
    anna_id = person_id(admin, "Anna Claes")
    body = {"user_id": anna_id, "quarter_start": "2027-01-01", "days": 12.5}
    response = admin.put("/api/projects/4102/planned-days", json=body)
    assert response.status_code == 200
    anna_row = next(r for r in response.json()["rows"] if r["person"]["name"] == "Anna Claes")
    cell = next(c for c in anna_row["cells"] if c["quarter_start"] == "2027-01-01")
    assert cell["planned"] == 12.5
    grid_before = response.json()["total_planned"]

    cleared = admin.put("/api/projects/4102/planned-days", json={**body, "days": 0})
    anna_row = next(r for r in cleared.json()["rows"] if r["person"]["name"] == "Anna Claes")
    assert next(c for c in anna_row["cells"] if c["quarter_start"] == "2027-01-01")["planned"] == 0
    assert cleared.json()["total_planned"] == pytest.approx(grid_before - 12.5)


def test_the_days_card_follows_a_changed_cell(admin: TestClient) -> None:
    before = admin.get("/api/projects/4102").json()["days"]["planned"]
    anna_id = person_id(admin, "Anna Claes")
    admin.put(
        "/api/projects/4102/planned-days",
        json={"user_id": anna_id, "quarter_start": "2027-04-01", "days": 10},
    )
    after = admin.get("/api/projects/4102").json()["days"]["planned"]
    assert after == pytest.approx(before + 10)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"days": 12.25}, "steps of 0.5"),
        ({"days": 70}, "only 66 workdays"),
        ({"quarter_start": "2026-10-02"}, "first day of a quarter"),
        ({"user_id": 999_999}, "involved in the project"),
    ],
)
def test_cell_rules_are_422(admin: TestClient, override: dict[str, Any], message: str) -> None:
    body = {
        "user_id": person_id(admin, "Anna Claes"),
        "quarter_start": "2026-10-01",
        "days": 5,
        **override,
    }
    response = admin.put("/api/projects/4102/planned-days", json=body)
    assert response.status_code == 422
    assert message in response.json()["message"]
    assert (
        admin.put("/api/projects/4102/planned-days", json={**body, "days": -1}).status_code == 422
    )


def test_a_non_member_has_no_planned_days(admin: TestClient) -> None:
    hilde = person_id(admin, "Hilde Casteels")
    response = admin.put(
        "/api/projects/4102/planned-days",
        json={"user_id": hilde, "quarter_start": "2027-01-01", "days": 2},
    )
    assert response.status_code == 422


def test_viewing_and_editing_the_grid_needs_the_rights(
    anna: TestClient, clients: ClientFactory
) -> None:
    assert anna.get("/api/projects/4102/planned-days").status_code == 200  # visible to viewers
    body = {"user_id": person_id(anna, "Anna Claes"), "quarter_start": "2027-01-01", "days": 1}
    assert anna.put("/api/projects/4102/planned-days", json=body).status_code == 403
    visitor = clients()
    assert visitor.get("/api/projects/4102/planned-days").status_code == 401
    assert visitor.put("/api/projects/4102/planned-days", json=body).status_code == 401
    assert anna.get("/api/projects/1/planned-days").status_code == 404


def test_people_who_booked_without_being_members_are_listed_separately(
    admin: TestClient, sample_database: Database, sample: Sample
) -> None:
    """[PD-5] Time is booked on #4102 by a person who is then removed from the project."""
    spec = next(p for p in sample.projects if p.number == 4102)
    booker = next(
        m
        for m in spec.members
        if m != spec.coordinator
        and any(e.person == m and e.project == 4102 for e in sample.entries)
    )
    user_id = person_id(admin, booker)
    assert admin.delete(f"/api/projects/4102/members/{user_id}").status_code == 200
    grid = admin.get("/api/projects/4102/planned-days").json()
    also = {r["person"]["name"]: r for r in grid["also_booked"]}
    assert booker in also
    assert also[booker]["is_member"] is False
    assert also[booker]["planned_total"] == 0
    expected = (
        sum(e.minutes for e in sample.entries if e.person == booker and e.project == 4102) / 480
    )
    assert also[booker]["logged_total"] == pytest.approx(expected)
    with sample_database.session() as session:
        assert session.scalar(select(User.status).where(User.id == user_id)) is not None
