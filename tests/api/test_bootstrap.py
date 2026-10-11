"""The bootstrap document: reference data for the whole app, never projects. [SH-12]"""

import gzip
import json

from fastapi.testclient import TestClient

from momato.services.sample_data import Sample
from tests.api.conftest import ClientFactory
from tests.helpers import count_statements


def test_a_visitor_is_told_to_sign_in(clients: ClientFactory) -> None:
    response = clients().get("/api/bootstrap")
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_required"


def test_the_bootstrap_holds_the_org_tree_people_statuses_plans_and_profile(
    anna: TestClient, sample: Sample
) -> None:
    """[DT-1] [SH-3]"""
    body = anna.get("/api/bootstrap").json()
    assert body["today"] == "2026-10-08"
    assert body["me"]["name"] == "Anna Claes"
    assert len(body["org"]) == len(sample.org) + 1
    assert body["org"][0]["parent_id"] is None  # the root comes first
    assert len(body["people"]) == len(sample.people)
    assert all(p["active"] for p in body["people"])
    assert {"Administrator", "Anonymous visitor"}.isdisjoint(p["name"] for p in body["people"])
    anna_row = next(p for p in body["people"] if p["name"] == "Anna Claes")
    assert anna_row["work_minutes"] == [480] * 5
    eva = next(p for p in body["people"] if p["name"] == "Eva Janssens")
    assert eva["work_minutes"] == [480, 480, 480, 480, 0]

    assert [s["key"] for s in body["statuses"]] == [
        "idea",
        "rejected",
        "preparation",
        "progress",
        "hold",
        "stopped",
        "finished",
    ]
    assert [s["key"] for s in body["statuses"] if s["hidden"]] == ["stopped"]
    assert [p["key"] for p in body["priorities"]] == ["high", "medium", "low"]

    assert len(body["plans"]) == len(sample.plans)
    digital = next(p for p in body["plans"] if p["name"] == "Digital plant")
    expected = next(p for p in sample.plans if p.name == "Digital plant")
    assert digital["project_count"] == len(expected.projects)  # Anna may see all (defaults)

    profile = body["profile"]
    assert profile["name"] == "default"
    assert [c["title"] for c in profile["cards"]] == [
        "Identification",
        "Organisation",
        "Classification",
        "Involvement",
    ]
    assert profile["hours_per_day"] == 8
    assert [c["key"] for c in profile["categories"]][:3] == ["meetings", "training", "admin"]


def test_the_bootstrap_never_contains_projects(anna: TestClient) -> None:
    body = anna.get("/api/bootstrap").json()
    assert "projects" not in body
    text = json.dumps(body)
    assert "Sensor retrofit on conveyor 4" not in text  # not even a name


def test_the_bootstrap_stays_under_300_kb_compressed(anna: TestClient) -> None:
    """[§8.5]"""
    raw = anna.get("/api/bootstrap", headers={"Accept-Encoding": "identity"}).content
    assert len(gzip.compress(raw)) < 300_000


def test_the_bootstrap_costs_a_fixed_number_of_statements(anna: TestClient) -> None:
    with count_statements() as counter:
        anna.get("/api/bootstrap")
    assert counter.count <= 15  # a fixed number: nothing grows with people, projects or plans


def test_each_person_sees_the_plan_counts_of_their_own_visible_projects(
    clients: ClientFactory, admin: TestClient
) -> None:
    body = admin.get("/api/bootstrap").json()
    assert body["me"]["is_system"] is True
    assert len(body["plans"]) == 12
