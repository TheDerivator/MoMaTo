"""Server-side pickers: projects and people, as the user types. [SH-12] [SH-6] [PD-4] [TS-8]"""

from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from momato.db.models import DefaultGrant, User
from momato.db.models.people import UserStatus
from momato.db.session import Database
from momato.domain.projects import BOOKABLE_STATUSES, ProjectStatus
from momato.services.sample_data import Sample
from tests.api.conftest import ClientFactory


def test_projects_are_found_by_name_or_number_highest_first(
    anna: TestClient, sample: Sample
) -> None:
    hits = anna.get("/api/search/projects", params={"q": "sensor"}).json()
    expected = sorted(
        (p.number for p in sample.projects if "sensor" in p.name.casefold()), reverse=True
    )
    assert [h["number"] for h in hits] == expected[:20]
    assert hits[0].keys() >= {"number", "name", "status", "org_node_name"}
    by_number = anna.get("/api/search/projects", params={"q": "#4102"}).json()
    assert 4102 in [h["number"] for h in by_number]


def test_search_includes_stopped_projects_unlike_the_list(anna: TestClient, sample: Sample) -> None:
    stopped = next(p for p in sample.projects if p.status is ProjectStatus.STOPPED)
    hits = anna.get("/api/search/projects", params={"q": str(stopped.number)}).json()
    assert stopped.number in [h["number"] for h in hits]


def test_bookable_keeps_projects_in_preparation_or_in_progress(
    anna: TestClient, sample: Sample
) -> None:
    hits = anna.get("/api/search/projects", params={"bookable": True}).json()
    assert hits
    assert {h["status"] for h in hits} <= {s.value for s in BOOKABLE_STATUSES}
    expected = sorted(
        (p.number for p in sample.projects if p.status in BOOKABLE_STATUSES), reverse=True
    )
    assert [h["number"] for h in hits] == expected[:20]


def test_at_most_twenty_hits_and_an_empty_query_lists_the_newest(anna: TestClient) -> None:
    hits = anna.get("/api/search/projects").json()
    assert len(hits) == 20
    numbers = [h["number"] for h in hits]
    assert numbers == sorted(numbers, reverse=True)


def test_search_only_finds_what_the_caller_may_see(
    clients: ClientFactory, sample_database: Database, sample: Sample
) -> None:
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))
    tomas = clients("tomas.rivera")
    hits = tomas.get("/api/search/projects").json()
    mine = {p.number for p in sample.projects if "Tomás Rivera" in p.members}
    assert {h["number"] for h in hits} <= mine
    assert {h["number"] for h in hits} == set(sorted(mine, reverse=True)[:20])


def test_people_are_found_by_name_or_job_title(anna: TestClient, sample: Sample) -> None:
    hits = anna.get("/api/search/people", params={"q": "CLAES"}).json()
    assert [h["name"] for h in hits] == ["Anna Claes"]
    by_title = anna.get("/api/search/people", params={"q": "furnace technologist"}).json()
    assert [h["name"] for h in by_title] == ["Tom Hendrickx"]
    everyone = anna.get("/api/search/people").json()
    assert len(everyone) == 20
    assert [h["name"] for h in everyone] == sorted(h["name"] for h in everyone)
    assert {"id", "name", "job_title", "org_node_id", "hue"} <= set(everyone[0])
    assert len(sample.people) > 20


def test_system_accounts_and_deactivated_people_are_never_offered(
    anna: TestClient, sample_database: Database
) -> None:
    assert anna.get("/api/search/people", params={"q": "administrator"}).json() == []
    assert anna.get("/api/search/people", params={"q": "anonymous"}).json() == []
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.name == "Bram Peeters").values(status=UserStatus.DEACTIVATED)
        )
    assert anna.get("/api/search/people", params={"q": "peeters"}).json() == []


def test_a_visitor_gets_401(clients: ClientFactory) -> None:
    visitor = clients()
    assert visitor.get("/api/search/projects").status_code == 401
    assert visitor.get("/api/search/people").status_code == 401
