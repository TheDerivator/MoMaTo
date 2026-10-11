"""People planning API: buckets for the pinned date, planned / spent / compare cells, hours
privacy, drill-down lines, and the statement count. [PPL-1] [PPL-2] [PPL-3] [PPL-4] [PPL-5]
[PPL-6] [PPL-7] [R4.3] [R4.5] [R4.11]"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select

from momato.db.models import DefaultGrant, OrgNode, TimeEntry, User
from momato.db.models.people import UserKind
from momato.db.session import Database
from momato.domain.access import BuiltinRole, Scope
from momato.domain.calendar import Quarter
from momato.domain.capacity import (
    WorkPattern,
    available_minutes,
    compare_class,
    load_class,
    quarter_availability_days,
    year_availability_days,
)
from momato.domain.planning import planned_in_period
from momato.services.sample_data import PersonSpec, Sample
from tests.api.conftest import ClientFactory, grant
from tests.helpers import count_statements

TODAY = date(2026, 10, 8)
OFF = {"vacation", "out_of_office"}
MINUTES_PER_DAY = 480


def get(
    client: TestClient, mode: str = "planned", period: str = "week", **params: Any
) -> dict[str, Any]:
    response = client.get("/api/people-planning", params={"mode": mode, "period": period, **params})
    assert response.status_code == 200, response.text
    return response.json()


def row_of(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in body["rows"] if r["person"]["name"] == name)


def names(body: dict[str, Any]) -> list[str]:
    return [r["person"]["name"] for r in body["rows"]]


def person_spec(sample: Sample, name: str) -> PersonSpec:
    return next(p for p in sample.people if p.name == name)


def pattern_of(spec: PersonSpec) -> WorkPattern:
    return WorkPattern(spec.pattern)


def planned_by_quarter(sample: Sample, name: str) -> dict[Quarter, Fraction]:
    result: dict[Quarter, Fraction] = defaultdict(Fraction)
    for project in sample.projects:
        for (person, quarter), days in project.planned.items():
            if person == name:
                result[Quarter.containing(quarter)] += Fraction(days)
    return result


def node_id(client: TestClient, name: str) -> int:
    return next(n["id"] for n in client.get("/api/bootstrap").json()["org"] if n["name"] == name)


def person_id(client: TestClient, name: str) -> int:
    return next(p["id"] for p in client.get("/api/bootstrap").json()["people"] if p["name"] == name)


def spent_minutes(sample: Sample, name: str, start: date, end: date, *, members_only: bool) -> int:
    members = {p.number for p in sample.projects if name in p.members}
    total = 0
    for entry in sample.entries:
        if entry.person != name or not start <= entry.day <= end:
            continue
        if entry.category in OFF:
            continue
        if members_only and (entry.project is None or entry.project not in members):
            continue
        total += entry.minutes
    return total


def time_off_minutes(sample: Sample, name: str, start: date, end: date) -> int:
    return sum(
        e.minutes
        for e in sample.entries
        if e.person == name and e.category in OFF and start <= e.day <= end
    )


# ---------------------------------------------------------------- buckets


def test_planned_has_eight_quarters_and_the_current_one_is_marked(anna: TestClient) -> None:
    body = get(anna, "planned")
    assert [b["key"] for b in body["buckets"]] == [
        f"Q{q}/{y}" for y in (26, 27) for q in (1, 2, 3, 4)
    ]
    assert body["unit"] == "days"
    assert body["range_label"] == "Quarters 2026 – 2027 · days"
    assert [b["key"] for b in body["buckets"] if b["current"]] == ["Q4/26"]
    assert body["hidden_count"] == 0  # planned is for everyone who may see projects somewhere
    assert body["total_count"] == len(body["rows"]) == 70


def test_spent_buckets_for_the_pinned_thursday(anna: TestClient) -> None:
    week = get(anna, "spent", "week")
    assert week["unit"] == "hours"
    assert week["range_label"] == "Week 40 · 28 Sep – 2 Oct 2026 · hours"
    assert [(b["key"], b["sub"]) for b in week["buckets"]] == [
        ("Mon", "28 Sep"),
        ("Tue", "29 Sep"),
        ("Wed", "30 Sep"),
        ("Thu", "1 Oct"),
        ("Fri", "2 Oct"),
    ]
    month = get(anna, "spent", "month")
    assert month["unit"] == "days"
    assert [b["key"] for b in month["buckets"]] == ["Wk 37", "Wk 38", "Wk 39", "Wk 40"]
    assert [b["start"] for b in month["buckets"]] == [
        "2026-09-07",
        "2026-09-14",
        "2026-09-21",
        "2026-09-28",
    ]
    year = get(anna, "spent", "year")
    assert [b["key"] for b in year["buckets"]] == [
        "Oct",
        "Nov",
        "Dec",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
    ]
    assert year["buckets"][0]["sub"] == "’25" and year["buckets"][-1]["sub"] == "’26"
    assert (
        year["buckets"][0]["start"] == "2025-10-01" and year["buckets"][-1]["end"] == "2026-09-30"
    )
    assert year["range_label"] == "October 2025 – September 2026 · days"


def test_unknown_modes_periods_and_nodes_are_refused(anna: TestClient) -> None:
    assert anna.get("/api/people-planning", params={"mode": "nonsense"}).status_code == 422
    assert anna.get("/api/people-planning", params={"period": "decade"}).status_code == 422
    assert anna.get("/api/people-planning", params={"node": 999999}).status_code == 404
    assert anna.get("/api/people-planning/999999").status_code == 404


def test_visitors_get_401(clients: ClientFactory) -> None:
    assert clients().get("/api/people-planning").status_code == 401


# ---------------------------------------------------------------- planned


def test_planned_cells_are_the_planned_days_against_the_quarters_availability(
    anna: TestClient, sample: Sample
) -> None:
    body = get(anna, "planned")
    spec = person_spec(sample, "Anna Claes")
    planned = planned_by_quarter(sample, "Anna Claes")
    row = row_of(body, "Anna Claes")
    year_days = {2026: Fraction(245), 2027: Fraction(220)}  # an override for 2026 (D-020)
    for cell, bucket in zip(row["cells"], body["buckets"], strict=True):
        quarter = Quarter.containing(date.fromisoformat(bucket["start"]))
        days = planned.get(quarter, Fraction(0))
        capacity = quarter_availability_days(year_days[quarter.year], quarter)
        assert cell["value"] == pytest.approx(float(days))
        assert cell["reference"] == pytest.approx(float(capacity))
        assert cell["cls"] == load_class(days, capacity).value
    total = row["total"]
    this_year = sum(planned.get(Quarter(2026, q), Fraction(0)) for q in (1, 2, 3, 4))
    assert total["value"] == pytest.approx(float(this_year))
    assert total["reference"] == 245
    assert total["free"] == pytest.approx(float(245 - this_year))
    assert spec.availability[2026] == Decimal(245)


def test_a_four_day_pattern_and_an_override_follow_into_the_free_days(
    anna: TestClient, sample: Sample
) -> None:
    body = get(anna, "planned")
    eva = row_of(body, "Eva Janssens")  # four days a week: 220 × 0.8, no override
    assert eva["total"]["reference"] == pytest.approx(220 * 0.8)
    pattern = pattern_of(person_spec(sample, "Eva Janssens"))
    assert year_availability_days(None, pattern, 220) == Fraction(176)
    dries = row_of(body, "Dries Wouters")  # an override of 190 days for 2026
    assert dries["total"]["reference"] == 190
    planned = sum(
        planned_by_quarter(sample, "Dries Wouters").get(Quarter(2026, q), Fraction(0))
        for q in (1, 2, 3, 4)
    )
    assert dries["total"]["free"] == pytest.approx(float(190 - planned))


# ---------------------------------------------------------------- spent


def test_spent_equals_the_entries_without_time_off_and_capacity_subtracts_time_off(
    anna: TestClient, sample: Sample
) -> None:
    body = get(anna, "spent", "year")
    for name in ("Anna Claes", "Eva Janssens", "Katrien Dumon"):
        try:
            row = row_of(body, name)
        except StopIteration:  # her hours are not visible to Anna (another department)
            continue
        pattern = pattern_of(person_spec(sample, name))
        for cell, bucket in zip(row["cells"], body["buckets"], strict=True):
            start, end = date.fromisoformat(bucket["start"]), date.fromisoformat(bucket["end"])
            minutes = spent_minutes(sample, name, start, end, members_only=False)
            assert cell["value"] == pytest.approx(minutes / MINUTES_PER_DAY), (name, bucket["key"])
            off = time_off_minutes(sample, name, start, end)
            available = available_minutes(pattern, start, end, off)
            assert cell["reference"] == pytest.approx(available / MINUTES_PER_DAY)
            assert (
                cell["cls"]
                == load_class(
                    Fraction(minutes, MINUTES_PER_DAY), Fraction(available, MINUTES_PER_DAY)
                ).value
            )
        assert row["total"]["value"] == pytest.approx(sum(c["value"] for c in row["cells"]))


def test_the_week_period_is_in_hours(anna: TestClient, sample: Sample) -> None:
    body = get(anna, "spent", "week")
    row = row_of(body, "Anna Claes")
    for cell, bucket in zip(row["cells"], body["buckets"], strict=True):
        day = date.fromisoformat(bucket["start"])
        minutes = spent_minutes(sample, "Anna Claes", day, day, members_only=False)
        assert cell["value"] == pytest.approx(minutes / 60)


# ---------------------------------------------------------------- compare


def test_compare_counts_member_projects_only_against_the_plan(
    anna: TestClient, sample: Sample
) -> None:
    body = get(anna, "compare", "year")
    row = row_of(body, "Anna Claes")
    spec = person_spec(sample, "Anna Claes")
    pattern = pattern_of(spec)
    planned = planned_by_quarter(sample, "Anna Claes")
    for cell, bucket in zip(row["cells"], body["buckets"], strict=True):
        start, end = date.fromisoformat(bucket["start"]), date.fromisoformat(bucket["end"])
        spent = Fraction(
            spent_minutes(sample, "Anna Claes", start, end, members_only=True), MINUTES_PER_DAY
        )
        reference = planned_in_period(planned, pattern, start, end)
        assert cell["value"] == pytest.approx(float(spent))
        assert cell["reference"] == pytest.approx(float(reference))
        assert cell["cls"] == compare_class(spent, reference).value
    total_spent = sum(c["value"] for c in row["cells"])
    total_planned = sum(c["reference"] for c in row["cells"])
    assert row["total"]["percent"] == round(total_spent * 100 / total_planned)


# ---------------------------------------------------------------- privacy


def test_hours_privacy_matrix(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    """[PPL-6] own time always; the department through the default grant; a global Hours viewer
    sees all; others are counted, not shown."""
    in_stl = {p.name for p in sample.people if p.node.split("/")[0] == "STL"}
    assert len(in_stl) == 11

    anna = clients("anna.claes")
    spent = get(anna, "spent", "month")
    assert set(names(spent)) == in_stl  # her department (STL), through the default grant
    assert spent["hidden_count"] == 70 - 11
    assert spent["total_count"] == 70

    planned = get(anna, "planned")  # planned is shown to anyone who may view projects
    assert len(planned["rows"]) == 70 and planned["hidden_count"] == 0

    # outside her branch: Planned is there, Spent and Compare are not
    it_node = node_id(anna, "IT & automation")
    outside = get(anna, "spent", "month", node=it_node)
    assert outside["rows"] == [] and outside["hidden_count"] == 9
    compare = get(anna, "compare", "month", node=it_node)
    assert compare["rows"] == [] and compare["hidden_count"] == 9
    assert len(get(anna, "planned", node=it_node)["rows"]) == 9

    # a department head with a global Hours viewer role sees all
    grant(sample_database, "tomas.rivera", BuiltinRole.HOURS_VIEWER, Scope.everywhere())
    head = clients("tomas.rivera")
    everyone = get(head, "spent", "month")
    assert len(everyone["rows"]) == 70 and everyone["hidden_count"] == 0


def test_a_person_sees_their_own_time_even_with_no_grant(
    clients: ClientFactory, sample_database: Database
) -> None:
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))
    tomas = clients("tomas.rivera")
    body = get(tomas, "spent", "month")
    assert names(body) == ["Tomás Rivera"]
    assert body["hidden_count"] == 69
    assert (
        tomas.get(f"/api/people-planning/{person_id(tomas, 'Anna Claes')}?mode=spent").status_code
        == 403
    )


# ---------------------------------------------------------------- the branch and the filter


def test_the_branch_and_the_name_filter_narrow_the_rows(anna: TestClient, sample: Sample) -> None:
    it_node = node_id(anna, "IT & automation")
    branch = get(anna, "planned", node=it_node)
    expected = {p.name for p in sample.people if p.node.split("/")[0] == "IT & automation"}
    assert set(names(branch)) == expected
    narrowed = get(anna, "planned", node=it_node, q="rivera")
    assert names(narrowed) == ["Tomás Rivera"]
    sub = node_id(anna, "Level 1-2 automation")
    inner = {p.name for p in sample.people if p.node == "IT & automation/Level 1-2 automation"}
    assert set(names(get(anna, "planned", node=sub))) == inner
    assert names(get(anna, "planned", q="zzzz")) == []


# ---------------------------------------------------------------- drill-down


def test_a_persons_planned_lines_are_their_member_projects(
    anna: TestClient, sample: Sample
) -> None:
    body = anna.get(
        f"/api/people-planning/{person_id(anna, 'Anna Claes')}", params={"mode": "planned"}
    ).json()
    assert body["person"]["name"] == "Anna Claes" and body["unit"] == "days"
    by_number = {line["number"]: line for line in body["lines"] if line["kind"] == "project"}
    expected = {
        p.number
        for p in sample.projects
        if any(person == "Anna Claes" and d > 0 for (person, _), d in p.planned.items())
    }
    assert set(by_number) == expected
    spec = next(p for p in sample.projects if p.number == 4102)
    q4 = next(i for i, b in enumerate(body["buckets"]) if b["key"] == "Q4/26")
    assert by_number[4102]["cells"][q4]["value"] == pytest.approx(
        float(spec.planned[("Anna Claes", date(2026, 10, 1))])
    )
    assert all(line["total"]["value"] > 0 for line in by_number.values())


def test_spent_lines_have_other_work_and_time_off(anna: TestClient, sample: Sample) -> None:
    body = anna.get(
        f"/api/people-planning/{person_id(anna, 'Anna Claes')}",
        params={"mode": "spent", "period": "year"},
    ).json()
    kinds = [line["kind"] for line in body["lines"]]
    assert kinds[-2:] == ["other_work", "time_off"] or kinds[-1] == "other_work"
    work = next(line for line in body["lines"] if line["kind"] == "other_work")
    start, end = date(2025, 10, 1), date(2026, 9, 30)
    expected = sum(
        e.minutes
        for e in sample.entries
        if e.person == "Anna Claes"
        and e.project is None
        and e.category not in OFF
        and start <= e.day <= end
    )
    assert work["total"]["value"] == pytest.approx(expected / MINUTES_PER_DAY)
    projects = sum(line["total"]["value"] for line in body["lines"] if line["kind"] == "project")
    all_spent = spent_minutes(sample, "Anna Claes", start, end, members_only=False)
    assert projects + work["total"]["value"] == pytest.approx(all_spent / MINUTES_PER_DAY)


def test_compare_lines_split_member_projects_from_other_bookings(
    anna: TestClient, sample_database: Database, sample: Sample
) -> None:
    # Anna books on a project she is not a member of
    with sample_database.session(write=True) as session:
        anna_id = session.scalar(select(User.id).where(User.username == "anna.claes"))
        assert anna_id is not None
        number = next(
            p.number
            for p in sample.projects
            if "Anna Claes" not in p.members and p.status.value == "progress"
        )
        from momato.db.models import Project

        project_id = session.scalar(select(Project.id).where(Project.number == number))
        session.add(
            TimeEntry(
                user_id=anna_id, work_date=date(2026, 9, 29), project_id=project_id, minutes=240
            )
        )
    body = anna.get(
        f"/api/people-planning/{person_id(anna, 'Anna Claes')}",
        params={"mode": "compare", "period": "month"},
    ).json()
    other = [line for line in body["lines"] if line["kind"] == "non_member"]
    assert [line["number"] for line in other] == [number]
    assert other[0]["total"]["value"] == pytest.approx(0.5)  # 4 h at 8 h per day
    assert other[0]["cells"][3]["cls"] == "unplanned"  # nothing was planned: red
    members = [line for line in body["lines"] if line["kind"] == "project"]
    assert members and all(line["number"] != number for line in members)


def test_projects_the_viewer_cannot_see_are_summed_into_other_projects(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    """[PPL-7]"""
    grant(sample_database, "bram.peeters", BuiltinRole.HOURS_VIEWER, Scope.everywhere())
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))  # nobody sees projects by default any more
    bram = clients("bram.peeters")
    anna_id = person_id(bram, "Anna Claes")
    body = bram.get(
        f"/api/people-planning/{anna_id}", params={"mode": "spent", "period": "year"}
    ).json()
    kinds = {line["kind"] for line in body["lines"]}
    assert "other_projects" in kinds and "project" not in kinds  # Bram sees none of her projects
    other = next(line for line in body["lines"] if line["kind"] == "other_projects")
    work = next(line for line in body["lines"] if line["kind"] == "other_work")
    start, end = date(2025, 10, 1), date(2026, 9, 30)
    all_spent = spent_minutes(sample, "Anna Claes", start, end, members_only=False)
    assert other["total"]["value"] + work["total"]["value"] == pytest.approx(
        all_spent / MINUTES_PER_DAY
    )
    # the totals in the table always include them
    table = get(bram, "spent", "year")
    assert row_of(table, "Anna Claes")["total"]["value"] == pytest.approx(
        all_spent / MINUTES_PER_DAY
    )


# ---------------------------------------------------------------- scale


def test_the_number_of_statements_does_not_depend_on_the_number_of_people(
    clients: ClientFactory, sample_database: Database
) -> None:
    admin = clients("admin", "admin-password-for-tests")
    paths = [
        {"mode": "planned"},
        {"mode": "spent", "period": "year"},
        {"mode": "compare", "period": "month"},
    ]

    def counts() -> list[int]:
        result = []
        for params in paths:
            with count_statements() as counter:
                response = admin.get("/api/people-planning", params=params)
            assert response.status_code == 200
            result.append(counter.count)
        return result

    before = counts()
    with sample_database.session(write=True) as session:
        node = session.scalar(select(OrgNode.id).where(OrgNode.parent_id.is_not(None)))
        session.execute(
            insert(User),
            [
                {
                    "kind": UserKind.PERSON,
                    "name": f"Bulk Person {index:04d}",
                    "org_node_id": node,
                    "hue": 120,
                    "status": "active",
                    "work_minutes_mon": 480,
                    "work_minutes_tue": 480,
                    "work_minutes_wed": 480,
                    "work_minutes_thu": 480,
                    "work_minutes_fri": 480,
                    "must_change_password": False,
                }
                for index in range(400)
            ],
        )
        ids = list(session.scalars(select(User.id).where(User.name.like("Bulk Person%"))))
        session.execute(
            insert(TimeEntry),
            [
                {
                    "user_id": user_id,
                    "work_date": TODAY - timedelta(days=14),
                    "category_key": "meetings",
                    "minutes": 120,
                }
                for user_id in ids
            ],
        )
    after = counts()
    assert after == before
