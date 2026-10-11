"""The timesheet API: a week's lines and state, setting cells under R4.8's rules, submitting, and
the week card of the bootstrap. [TS-1] [TS-2] [TS-4] [TS-6] [TS-7] [TS-9] [TS-10] [TS-13] [TS-15]
[R4.8] [R4.9]"""

from datetime import date
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from momato.db.models import DefaultGrant, TimeEntry, User, WeekSubmission
from momato.db.session import Database
from momato.domain.calendar import IsoWeek, Quarter
from momato.domain.capacity import WorkPattern
from momato.domain.planning import weekly_planned_hours
from momato.services.sample_data import Sample
from tests.api.conftest import ClientFactory

WEEK = "2026-W41"  # Monday 5 to Friday 9 October 2026; the pinned today is Thursday the 8th
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY = (date(2026, 10, d) for d in range(5, 10))


def get(client: TestClient, week: str | None = None) -> dict[str, Any]:
    response = client.get("/api/timesheet" + (f"/{week}" if week else ""))
    assert response.status_code == 200, response.text
    return response.json()


def put(client: TestClient, day: date, line: str, task: str, minutes: int, week: str = WEEK) -> Any:
    return client.put(
        f"/api/timesheet/{week}/cells",
        json={"day": day.isoformat(), "line": line, "task": task, "minutes": minutes},
    )


def line_of(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(line for line in body["lines"] if line["key"] == key)


def task_key(body: dict[str, Any], line: str, name: str) -> str:
    return next(c["key"] for c in line_of(body, line)["choices"] if c["name"] == name)


# ---------------------------------------------------------------- reading


def test_the_current_week_is_anna_claes_design_week(anna: TestClient, sample: Sample) -> None:
    body = get(anna)
    assert body["week"] == WEEK
    assert body["is_current"] is True
    assert body["today_index"] == 3
    assert (body["monday"], body["friday"]) == ("2026-10-05", "2026-10-09")
    assert body["next"] is None and body["previous"] == "2026-W40"
    assert body["step_minutes"] == 60 and body["cap_minutes"] == 600

    assert [d["target_minutes"] for d in body["days"]] == [480] * 5
    assert [d["minutes"] for d in body["days"]] == [480, 480, 0, 0, 0]
    assert [d["tag"] for d in body["days"]] == ["done", "done", "", "today", "next"]
    state = body["state"]
    assert state["state"] == "partial"
    assert state["title"] == "Two days done!"
    assert state["headline"] == "Two days done, 3 to go"
    assert state["subline"] == "16 of 40 h logged. Next up: Wednesday."
    assert body["submitted"] is False


def test_lines_are_the_planned_projects_by_hours_then_other_work_and_time_off(
    anna: TestClient, sample: Sample
) -> None:
    body = get(anna)
    keys = [line["key"] for line in body["lines"]]
    assert keys[-2:] == ["other_work", "time_off"]
    projects = [line for line in body["lines"] if line["kind"] == "project"]
    planned = [line["planned_minutes"] for line in projects if not line["unplanned"]]
    assert planned == sorted(planned, reverse=True)
    assert [round(p / 60) for p in planned] == [14, 10, 8, 4]  # the design's planned hours
    assert all(line["unplanned"] is False for line in projects)

    # a line's planned minutes are the domain's exact value
    spec = next(p for p in sample.projects if p.number == 4102)
    quarters = {
        Quarter.containing(q): Fraction(v)
        for (person, q), v in spec.planned.items()
        if person == "Anna Claes"
    }
    expected = weekly_planned_hours(quarters, WorkPattern(), IsoWeek.parse(WEEK), 8) * 60
    assert line_of(body, "project:4102")["planned_minutes"] == pytest.approx(float(expected))


def test_cells_hold_minutes_per_task_and_weekday(anna: TestClient) -> None:
    body = get(anna)
    sensors = line_of(body, "project:4102")
    installation = task_key(body, "project:4102", "Installation")
    assert sensors["minutes"] == {installation: [180, 240, 0, 0, 0]}
    other = line_of(body, "other_work")
    assert other["minutes"] == {"meetings": [60, 60, 0, 0, 0]}
    assert other["planned_minutes"] == 240  # 10 % of a 40 h week


def test_the_task_picker_offers_tasks_then_general_and_categories(anna: TestClient) -> None:
    body = get(anna)
    sensors = line_of(body, "project:4102")
    names = [c["name"] for c in sensors["choices"]]
    assert names[-1] == "General"
    assert "Installation" in names
    installation = next(c for c in sensors["choices"] if c["name"] == "Installation")
    assert installation["status"] == "running"
    assert [c["key"] for c in line_of(body, "other_work")["choices"]] == [
        "meetings",
        "training",
        "admin",
    ]
    assert [c["key"] for c in line_of(body, "time_off")["choices"]] == [
        "vacation",
        "out_of_office",
    ]
    assert line_of(body, "time_off")["planned_minutes"] is None  # no plan, no fill-up (TS-5)


def test_a_past_week_has_its_own_state_and_neighbours(anna: TestClient, sample: Sample) -> None:
    body = get(anna, "2026-W40")
    assert body["is_current"] is False
    assert body["today_index"] == 7
    assert body["previous"] == "2026-W39" and body["next"] == WEEK
    submitted = any(
        person == "Anna Claes" and week == IsoWeek.parse("2026-W40")
        for person, week in sample.submissions
    )
    assert body["submitted"] is submitted
    assert body["state"]["state"] in {"submitted", "full", "open", "partial", "fresh"}


def test_future_and_malformed_weeks_are_refused(anna: TestClient) -> None:
    assert anna.get("/api/timesheet/2026-W42").status_code == 422
    assert anna.get("/api/timesheet/2027-W01").status_code == 422
    assert anna.get("/api/timesheet/nonsense").status_code == 422
    assert anna.get("/api/timesheet/2026-W54").status_code == 422


def test_only_people_have_a_timesheet(clients: ClientFactory, admin: TestClient) -> None:
    assert clients().get("/api/timesheet").status_code == 401
    assert admin.get("/api/timesheet").status_code == 403  # a system account (TS-13)
    assert (
        admin.put(
            f"/api/timesheet/{WEEK}/cells",
            json={"day": "2026-10-06", "line": "other_work", "task": "meetings", "minutes": 60},
        ).status_code
        == 403
    )
    assert admin.post(f"/api/timesheet/{WEEK}/submit").status_code == 403


def test_everyone_sees_only_their_own_time(clients: ClientFactory) -> None:
    sofia = get(clients("sofia.lind"))
    anna = get(clients("anna.claes"))
    assert sofia["days"] != anna["days"] or sofia["lines"] != anna["lines"]
    # Sofia's cells are Sofia's: none of Anna's Installation hours show up on her card
    assert line_of(anna, "project:4102")["minutes"] != line_of(sofia, "project:4102")["minutes"]


# ---------------------------------------------------------------- booking


def test_setting_a_cell_is_absolute_and_repeating_it_changes_nothing(anna: TestClient) -> None:
    body = get(anna)
    installation = task_key(body, "project:4102", "Installation")
    first = put(anna, WEDNESDAY, "project:4102", installation, 120)
    assert first.status_code == 200
    again = put(anna, WEDNESDAY, "project:4102", installation, 120)
    assert again.status_code == 200
    assert first.json()["lines"] == again.json()["lines"]
    assert again.json()["days"][2]["minutes"] == 120
    assert line_of(again.json(), "project:4102")["minutes"][installation] == [180, 240, 120, 0, 0]
    assert get(anna)["days"][2]["minutes"] == 120  # and it is stored


def test_the_week_state_follows_the_booking(anna: TestClient) -> None:
    body = get(anna)
    installation = task_key(body, "project:4102", "Installation")
    full = put(anna, WEDNESDAY, "project:4102", installation, 480).json()
    assert full["days"][2]["full"] is True and full["days"][2]["tag"] == "done"
    assert full["state"]["title"] == "Three days done!"
    emptied = put(anna, MONDAY, "project:4102", installation, 0).json()
    assert emptied["days"][0]["minutes"] == 300  # 8 h minus the 3 h on this project
    other = put(anna, MONDAY, "other_work", "meetings", 0).json()
    assert other["days"][0]["minutes"] == 240
    assert other["days"][0]["open"] is True
    assert other["state"]["title"] == "Monday still open"
    assert other["state"]["cta"] == "Catch up →"
    # 4 h of Vacation on Monday fills it again: time off fills the day like work (R4.9)
    back = put(anna, MONDAY, "time_off", "vacation", 240).json()
    assert back["days"][0]["full"] is True
    assert back["state"]["state"] == "partial"


def test_a_cell_at_zero_is_removed(anna: TestClient, sample_database: Database) -> None:
    put(anna, FRIDAY, "other_work", "training", 60)
    with sample_database.session() as session:
        count = session.scalar(
            select(func.count()).select_from(TimeEntry).where(TimeEntry.work_date == FRIDAY)
        )
        assert count == 1
    put(anna, FRIDAY, "other_work", "training", 0)
    with sample_database.session() as session:
        count = session.scalar(
            select(func.count()).select_from(TimeEntry).where(TimeEntry.work_date == FRIDAY)
        )
        assert count == 0


def test_a_day_holds_at_most_the_cap_over_all_lines(anna: TestClient) -> None:
    """[R4.8]"""
    body = get(anna)
    installation = task_key(body, "project:4102", "Installation")
    assert put(anna, WEDNESDAY, "project:4102", installation, 600).status_code == 200
    over = put(anna, WEDNESDAY, "other_work", "meetings", 60)
    assert over.status_code == 422 and "at most 10 hours" in over.json()["message"]
    too_much = put(anna, WEDNESDAY, "project:4102", installation, 660)
    assert too_much.status_code == 422
    # taking time away is always allowed
    assert put(anna, WEDNESDAY, "project:4102", installation, 540).status_code == 200
    assert put(anna, WEDNESDAY, "other_work", "meetings", 60).status_code == 200


def test_values_must_be_whole_steps_and_not_negative(anna: TestClient) -> None:
    installation = task_key(get(anna), "project:4102", "Installation")
    assert put(anna, WEDNESDAY, "project:4102", installation, 90).status_code == 422
    assert put(anna, WEDNESDAY, "project:4102", installation, -60).status_code == 422
    assert put(anna, WEDNESDAY, "project:4102", installation, 0).status_code == 200


def test_only_working_days_of_the_week_can_be_booked(
    anna: TestClient, sample_database: Database
) -> None:
    saturday = date(2026, 10, 10)
    assert put(anna, saturday, "other_work", "meetings", 60).status_code == 422
    assert (
        put(anna, date(2026, 10, 12), "other_work", "meetings", 60).status_code == 422
    )  # next week
    assert (
        put(anna, date(2026, 10, 2), "other_work", "meetings", 60).status_code == 422
    )  # last week
    assert put(anna, FRIDAY, "other_work", "meetings", 60, week="2026-W42").status_code == 422
    # a day this person does not work: a part-timer's Wednesday
    with sample_database.session(write=True) as session:
        user = session.scalar(select(User).where(User.username == "anna.claes"))
        assert user is not None
        user.work_minutes_wed = 0
    assert put(anna, WEDNESDAY, "other_work", "meetings", 60).status_code == 422


def test_unknown_lines_tasks_and_categories_are_refused(anna: TestClient) -> None:
    assert put(anna, TUESDAY, "nonsense", "x", 60).status_code == 422
    assert put(anna, TUESDAY, "project:4102", "task:999999", 60).status_code == 404
    assert put(anna, TUESDAY, "project:4102", "meetings", 60).status_code == 422
    assert put(anna, TUESDAY, "project:999999", "general", 60).status_code == 404
    assert (
        put(anna, TUESDAY, "other_work", "vacation", 60).status_code == 422
    )  # a time off category
    assert put(anna, TUESDAY, "time_off", "meetings", 60).status_code == 422
    assert put(anna, TUESDAY, "project:abc", "general", 60).status_code == 422


def test_a_task_of_another_project_is_refused(anna: TestClient) -> None:
    tasks = anna.get("/api/projects/4120/tasks").json()
    assert tasks
    refused = put(anna, TUESDAY, "project:4102", f"task:{tasks[0]['id']}", 60)
    assert refused.status_code == 404


def test_an_unplanned_project_is_a_line_while_it_has_time(anna: TestClient) -> None:
    before = get(anna)
    assert "project:4340" not in [line["key"] for line in before["lines"]]
    booked = put(anna, TUESDAY, "project:4340", "general", 60).json()
    line = line_of(booked, "project:4340")
    assert line["unplanned"] is True and line["planned_minutes"] is None
    assert line["minutes"] == {"general": [0, 60, 0, 0, 0]}
    assert [c["name"] for c in line["choices"]][-1] == "General"
    assert (
        booked["lines"].index(line)
        == len([x for x in booked["lines"] if x["kind"] == "project"]) - 1
    )

    gone = put(anna, TUESDAY, "project:4340", "general", 0).json()
    assert "project:4340" not in [x["key"] for x in gone["lines"]]


def test_booking_on_a_project_you_cannot_see_is_refused(
    clients: ClientFactory, sample_database: Database
) -> None:
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))
    bram = clients("bram.peeters")  # a member of nothing, and now a viewer of nothing
    assert put(bram, TUESDAY, "project:4102", "general", 60).status_code == 404
    assert put(bram, TUESDAY, "other_work", "meetings", 60).status_code == 200


# ---------------------------------------------------------------- submitting


def test_submit_marks_the_week_and_any_change_reopens_it(
    anna: TestClient, sample_database: Database
) -> None:
    body = get(anna)
    assert body["submitted"] is False
    submitted = anna.post(f"/api/timesheet/{WEEK}/submit")
    assert submitted.status_code == 200
    state = submitted.json()
    assert state["submitted"] is True and state["submitted_at"] is not None
    assert state["state"]["state"] == "submitted"
    assert state["state"]["title"] == "Week 41 submitted ✓"
    assert state["state"]["headline"] == "Week submitted"
    assert state["state"]["subline"] == "16 hours logged. Enjoy the weekend."
    assert anna.post(f"/api/timesheet/{WEEK}/submit").json()["submitted"] is True  # idempotent

    same = put(anna, MONDAY, "other_work", "meetings", 60)  # the value it already has
    assert same.json()["submitted"] is True  # nothing changed, so it stays submitted
    changed = put(anna, MONDAY, "other_work", "meetings", 120).json()
    assert changed["submitted"] is False
    with sample_database.session() as session:
        left = session.scalar(
            select(func.count())
            .select_from(WeekSubmission)
            .join(User, User.id == WeekSubmission.user_id)
            .where(
                User.username == "anna.claes",
                WeekSubmission.iso_year == 2026,
                WeekSubmission.iso_week == 41,
            )
        )
        assert left == 0


def test_a_past_week_can_be_corrected_and_submitted(anna: TestClient) -> None:
    assert anna.post("/api/timesheet/2026-W40/submit").status_code == 200
    assert (
        put(anna, date(2026, 9, 30), "other_work", "meetings", 60, week="2026-W40").status_code
        == 200
    )
    assert anna.post("/api/timesheet/2026-W42/submit").status_code == 422


# ---------------------------------------------------------------- the week card


def test_the_bootstrap_has_the_week_card_of_the_caller(
    anna: TestClient, admin: TestClient, clients: ClientFactory
) -> None:
    card = anna.get("/api/bootstrap").json()["week_card"]
    assert card["week"] == WEEK and card["week_number"] == 41 and card["today_index"] == 3
    assert card["state"]["title"] == "Two days done!"
    assert card["state"]["subline"] == "16 of 40 h logged. Next up: Wednesday."
    assert [d["tag"] for d in card["days"]] == ["done", "done", "", "today", "next"]
    assert admin.get("/api/bootstrap").json()["week_card"] is None  # a system account


def test_the_card_follows_the_booking(anna: TestClient) -> None:
    installation = task_key(get(anna), "project:4102", "Installation")
    put(anna, WEDNESDAY, "project:4102", installation, 480)
    card = anna.get("/api/bootstrap").json()["week_card"]
    assert card["state"]["title"] == "Three days done!"


@pytest.mark.parametrize("path", ["/api/timesheet", f"/api/timesheet/{WEEK}"])
def test_reading_does_not_write(anna: TestClient, sample_database: Database, path: str) -> None:
    with sample_database.session() as session:
        before = session.scalar(select(func.count()).select_from(TimeEntry))
    assert anna.get(path).status_code == 200
    with sample_database.session() as session:
        assert session.scalar(select(func.count()).select_from(TimeEntry)) == before
