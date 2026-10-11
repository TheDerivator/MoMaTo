"""The paged project list, its counts and neighbours, computed from the sample.

[PL-1] [PL-2] [PL-3] [PL-7] [SH-12] [SH-6]
"""

from collections import Counter
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from momato.db.models import DefaultGrant
from momato.db.session import Database
from momato.domain.projects import ProjectStatus
from momato.services.sample_data import ProjectSpec, Sample
from tests.api.conftest import ClientFactory

HIDDEN = {ProjectStatus.STOPPED}


def numbers(sample: Sample, *, status: ProjectStatus | None = None) -> list[int]:
    """The list's numbers by the rules of PL-2 and PL-7, from the specs (highest first)."""
    chosen = [
        p for p in sample.projects if (p.status is status if status else p.status not in HIDDEN)
    ]
    return sorted((p.number for p in chosen), reverse=True)


def top(spec_node: str) -> str:
    return spec_node.split("/")[0]


def fetch_all(client: TestClient, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Follow `next_after` from the first page to the end."""
    rows: list[dict[str, Any]] = []
    after: int | None = None
    while True:
        query = dict(params or {})
        if after is not None:
            query["after"] = after
        page = client.get("/api/projects", params=query).json()
        rows.extend(page["items"])
        after = page["next_after"]
        if after is None:
            return rows


# ---------------------------------------------------------------- the list


def test_the_first_page_has_fifty_rows_highest_number_first_without_stopped(
    anna: TestClient, sample: Sample
) -> None:
    page = anna.get("/api/projects").json()
    expected = numbers(sample)
    assert [r["number"] for r in page["items"]] == expected[:50]
    assert page["total"] == len(expected)
    assert page["next_after"] == expected[49]
    assert all(r["status"] != "stopped" for r in page["items"])


def test_a_row_has_what_the_table_shows(anna: TestClient, sample: Sample) -> None:
    """[PL-4]"""
    row = anna.get("/api/projects", params={"q": "4102"}).json()["items"][0]
    assert row["number"] == 4102
    assert row["name"] == "Sensor retrofit on conveyor 4"
    assert row["org_node_name"] == "Level 1-2 automation"
    assert row["status"] == "progress"
    assert (row["start_date"], row["end_date"]) == ("2025-11-03", "2027-03-31")
    assert row["coordinator"]["name"] == "Tomás Rivera"
    spec = next(p for p in sample.projects if p.number == 4102)
    others = [m for m in spec.members if m != spec.coordinator]
    assert {m["name"] for m in row["members"]} == set(others)  # three others: all shown


def test_following_after_visits_every_project_once_in_order(
    anna: TestClient, sample: Sample
) -> None:
    rows = fetch_all(anna)
    assert [r["number"] for r in rows] == numbers(sample)


def test_the_stopped_chip_shows_only_stopped_projects(anna: TestClient, sample: Sample) -> None:
    rows = fetch_all(anna, {"status": "stopped"})
    assert [r["number"] for r in rows] == numbers(sample, status=ProjectStatus.STOPPED)
    assert rows
    page = anna.get("/api/projects", params={"status": "stopped"}).json()
    assert page["total"] == len(rows)


@pytest.mark.parametrize("status", [s for s in ProjectStatus if s not in HIDDEN])
def test_each_status_filters_the_list(
    anna: TestClient, sample: Sample, status: ProjectStatus
) -> None:
    rows = fetch_all(anna, {"status": status.value})
    assert [r["number"] for r in rows] == numbers(sample, status=status)


def test_paging_survives_projects_created_between_page_loads(
    admin: TestClient, sample: Sample
) -> None:
    """Keyset paging: a new project with the highest number shifts no row of later pages."""
    first = admin.get("/api/projects").json()
    created = admin.post(
        "/api/projects",
        json={
            "name": "Created while paging",
            "org_node_id": first_node(admin),
            "start_date": "2026-11-01",
            "end_date": "2027-01-31",
            "coordinator_id": first_person(admin),
        },
    )
    assert created.status_code == 201
    rest: list[int] = []
    after: int | None = first["next_after"]
    while after is not None:
        page = admin.get("/api/projects", params={"after": after}).json()
        rest.extend(r["number"] for r in page["items"])
        after = page["next_after"]
    seen = [r["number"] for r in first["items"]] + rest
    assert seen == numbers(sample)  # every old project exactly once, the new one not repeated
    assert len(seen) == len(set(seen))


def first_node(client: TestClient) -> int:
    body = client.get("/api/bootstrap").json()
    return next(n["id"] for n in body["org"] if n["name"] == "Quality")


def first_person(client: TestClient) -> int:
    body = client.get("/api/bootstrap").json()
    return next(p["id"] for p in body["people"] if p["name"] == "Anna Claes")


def test_the_limit_and_validation(anna: TestClient) -> None:
    assert len(anna.get("/api/projects", params={"limit": 7}).json()["items"]) == 7
    assert anna.get("/api/projects", params={"limit": 0}).status_code == 422
    assert anna.get("/api/projects", params={"limit": 101}).status_code == 422
    assert anna.get("/api/projects", params={"status": "nonsense"}).status_code == 422
    assert anna.get("/api/projects", params={"node": 999_999}).status_code == 404


# ---------------------------------------------------------------- filters


def test_a_branch_filters_the_list_and_its_total(anna: TestClient, sample: Sample) -> None:
    bootstrap = anna.get("/api/bootstrap").json()
    node = next(n for n in bootstrap["org"] if n["name"] == "Energy & utilities")
    rows = fetch_all(anna, {"node": node["id"]})
    expected = sorted(
        (
            p.number
            for p in sample.projects
            if top(p.node) == "Energy & utilities" and p.status not in HIDDEN
        ),
        reverse=True,
    )
    assert [r["number"] for r in rows] == expected
    assert {r["org_node_name"] for r in rows} <= {
        "Power & steam",
        "Water treatment",
        "Compressed air",
    }


def test_a_section_filters_to_its_own_projects(anna: TestClient, sample: Sample) -> None:
    bootstrap = anna.get("/api/bootstrap").json()
    node = next(n for n in bootstrap["org"] if n["name"] == "Power & steam")
    rows = fetch_all(anna, {"node": node["id"]})
    expected = sorted(
        (
            p.number
            for p in sample.projects
            if p.node.endswith("/Power & steam") and p.status not in HIDDEN
        ),
        reverse=True,
    )
    assert [r["number"] for r in rows] == expected


def matching(sample: Sample, predicate: Any) -> list[int]:
    return sorted(
        (p.number for p in sample.projects if predicate(p) and p.status not in HIDDEN), reverse=True
    )


def test_the_name_filter_is_a_case_insensitive_substring(anna: TestClient, sample: Sample) -> None:
    rows = fetch_all(anna, {"name": "SENSOR"})
    assert [r["number"] for r in rows] == matching(sample, lambda p: "sensor" in p.name.casefold())
    assert 4102 in [r["number"] for r in rows]


def test_the_coordinator_filter_is_unicode_aware(anna: TestClient, sample: Sample) -> None:
    rows = fetch_all(anna, {"coordinator": "TOMÁS"})  # É and Á fold like their lowercase
    assert [r["number"] for r in rows] == matching(
        sample, lambda p: "tomás" in p.coordinator.casefold()
    )
    assert {r["coordinator"]["name"] for r in rows} == {"Tomás Rivera"}
    assert fetch_all(anna, {"coordinator": "tomas"}) == []  # accents are not ignored


def test_search_finds_by_name_number_coordinator_and_org_node(
    anna: TestClient, sample: Sample
) -> None:
    def found(q: str) -> list[int]:
        return [r["number"] for r in fetch_all(anna, {"q": q})]

    assert found("pallet") == matching(sample, lambda p: "pallet" in p.name.casefold())
    assert found("#4102") == matching(sample, lambda p: "4102" in str(p.number))
    assert 4102 in found("4102")
    assert found("rivera") == matching(sample, lambda p: "rivera" in p.coordinator.casefold())
    assert found("galvanizing line 1") == matching(
        sample, lambda p: "galvanizing line 1" in p.node.split("/")[-1].casefold()
    )
    assert found("zzzz nothing") == []


def test_filters_combine(anna: TestClient, sample: Sample) -> None:
    rows = fetch_all(anna, {"q": "energy", "status": "progress", "name": "model"})
    expected = [
        p.number
        for p in sorted(sample.projects, key=lambda p: -p.number)
        if p.status is ProjectStatus.PROGRESS
        and "model" in p.name.casefold()
        and (
            "energy" in p.name.casefold()
            or "energy" in p.coordinator.casefold()
            or "energy" in p.node.split("/")[-1].casefold()
        )
    ]
    assert [r["number"] for r in rows] == expected


# ---------------------------------------------------------------- counts


def test_status_counts_cover_every_status_including_the_hidden_one(
    anna: TestClient, sample: Sample
) -> None:
    counts = anna.get("/api/projects/counts").json()
    expected = Counter(p.status.value for p in sample.projects)
    assert counts["statuses"] == {s.value: expected.get(s.value, 0) for s in ProjectStatus}
    assert counts["statuses"]["stopped"] > 0  # the chip stays visible with its count
    assert counts["total"] == len(numbers(sample))  # but the header leaves Stopped out


def test_node_counts_roll_up_the_tree_and_leave_hidden_statuses_out(
    anna: TestClient, sample: Sample
) -> None:
    counts = anna.get("/api/projects/counts").json()
    nodes = {n["id"]: n for n in anna.get("/api/bootstrap").json()["org"]}
    by_name = {n["name"]: n["id"] for n in nodes.values()}
    visible = [p for p in sample.projects if p.status not in HIDDEN]
    root_id = next(i for i, n in nodes.items() if n["parent_id"] is None)
    assert counts["nodes"][str(root_id)] == len(visible)
    for department in ("STL", "Hot rolling", "Central maintenance"):
        expected = sum(1 for p in visible if top(p.node) == department)
        assert counts["nodes"][str(by_name[department])] == expected
    mechanical = sum(1 for p in visible if p.node.startswith("Central maintenance/Mechanical"))
    assert counts["nodes"][str(by_name["Mechanical"])] == mechanical


def test_counts_follow_the_search_and_column_filters(anna: TestClient, sample: Sample) -> None:
    counts = anna.get("/api/projects/counts", params={"name": "sensor"}).json()
    expected = Counter(p.status.value for p in sample.projects if "sensor" in p.name.casefold())
    assert counts["statuses"] == {s.value: expected.get(s.value, 0) for s in ProjectStatus}
    wanted = [
        p for p in sample.projects if "sensor" in p.name.casefold() and p.status not in HIDDEN
    ]
    assert counts["total"] == len(wanted)


def test_status_counts_ignore_the_status_filter_but_follow_the_branch(
    anna: TestClient, sample: Sample
) -> None:
    node = next(n for n in anna.get("/api/bootstrap").json()["org"] if n["name"] == "Logistics")
    counts = anna.get("/api/projects/counts", params={"node": node["id"], "status": "idea"}).json()
    expected = Counter(p.status.value for p in sample.projects if top(p.node) == "Logistics")
    assert counts["statuses"] == {s.value: expected.get(s.value, 0) for s in ProjectStatus}
    # The tree follows the selected status, not the selected branch.
    ideas = [p for p in sample.projects if p.status is ProjectStatus.IDEA]
    root = next(n["id"] for n in anna.get("/api/bootstrap").json()["org"] if n["parent_id"] is None)
    assert counts["nodes"][str(root)] == len(ideas)
    assert counts["total"] == sum(1 for p in ideas if top(p.node) == "Logistics")


# ---------------------------------------------------------------- neighbours


def test_neighbours_follow_the_list_of_the_same_filters(anna: TestClient, sample: Sample) -> None:
    """[PP-1]"""
    expected = numbers(sample)
    middle = expected[100]
    body = anna.get(f"/api/projects/{middle}/neighbours").json()
    assert body == {
        "position": 101,
        "total": len(expected),
        "previous": expected[99],
        "next": expected[101],
        "in_list": True,
    }
    first = anna.get(f"/api/projects/{expected[0]}/neighbours").json()
    assert (first["position"], first["previous"], first["next"]) == (1, None, expected[1])
    last = anna.get(f"/api/projects/{expected[-1]}/neighbours").json()
    assert (last["position"], last["previous"], last["next"]) == (len(expected), expected[-2], None)


def test_neighbours_within_a_filtered_list(anna: TestClient, sample: Sample) -> None:
    expected = matching(sample, lambda p: "model" in p.name.casefold())
    assert len(expected) >= 3
    body = anna.get(f"/api/projects/{expected[1]}/neighbours", params={"name": "model"}).json()
    assert (body["position"], body["previous"], body["next"]) == (2, expected[0], expected[2])
    assert body["total"] == len(expected)


def test_a_project_outside_the_filtered_list_is_flagged(anna: TestClient, sample: Sample) -> None:
    body = anna.get("/api/projects/4102/neighbours", params={"status": "idea"}).json()
    assert body["in_list"] is False
    assert body["position"] is None
    ideas = [p.number for p in sample.projects if p.status is ProjectStatus.IDEA]
    assert body["total"] == len(ideas)
    assert body["previous"] == min((n for n in ideas if n > 4102), default=None)
    assert body["next"] == max((n for n in ideas if n < 4102), default=None)


def test_neighbours_of_an_unknown_project_are_404(anna: TestClient) -> None:
    assert anna.get("/api/projects/1/neighbours").status_code == 404


# ---------------------------------------------------------------- who sees what


def test_a_visitor_gets_401_and_a_person_without_view_rights_sees_only_their_own(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    """[SH-11] An invisible project is 404, like a missing one."""
    assert clients().get("/api/projects").status_code == 401
    with sample_database.session(write=True) as session:  # nobody is a Viewer by default any more
        session.execute(delete(DefaultGrant))
    tomas = clients("tomas.rivera")
    page = tomas.get("/api/projects").json()
    mine = sorted(
        (
            p.number
            for p in sample.projects
            if "Tomás Rivera" in p.members and p.status not in HIDDEN
        ),
        reverse=True,
    )
    assert [r["number"] for r in page["items"]] == mine
    assert page["total"] == len(mine)
    others = next(p for p in sample.projects if "Tomás Rivera" not in p.members)
    assert tomas.get(f"/api/projects/{others.number}").status_code == 404  # invisible: not found
    own: ProjectSpec = next(p for p in sample.projects if p.number == 4102)
    assert tomas.get(f"/api/projects/{own.number}").status_code == 200
    assert date.fromisoformat(page["items"][0]["start_date"])
