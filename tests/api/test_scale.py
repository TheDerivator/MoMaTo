"""The scale data set through the API: 5,000 projects, 500 people, two years of time (§8.5).

Run with `uv run pytest -m scale` before a release. The limits are the budgets of REQUIREMENTS 8.5
(measured in-process, so the network is not in them); a request is measured three times and the
best is held to the limit, which keeps a noisy laptop from failing it. [§8.5] [D-028]
"""

import gzip
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from momato.config import Settings
from momato.db.models import Project, TimeEntry, User
from momato.db.session import Database
from momato.web import create_app
from tests.conftest import DEMO_PASSWORD, SAMPLE_TODAY, _settings, start_client
from tests.helpers import login
from tests.scale import SCALE_PEOPLE, SCALE_PROJECTS, add_scale_data

pytestmark = pytest.mark.scale

DAYS = 365 * 2
LAST_WEEK = {"start": "2026-09-28", "end": "2026-10-02"}


@pytest.fixture(scope="session")
def scale_template(
    tmp_path_factory: pytest.TempPathFactory, sample_template_dir: Path | None
) -> Path:
    """A data dir with the sample data and the scale data set added, built once per run."""
    if sample_template_dir is None:
        pytest.skip("the scale data set is built on SQLite")
    folder = tmp_path_factory.mktemp("scale-template")
    shutil.copytree(sample_template_dir, folder, dirs_exist_ok=True)
    settings = _settings(folder)
    database = Database(settings.resolved_database_url)
    with database.session(write=True) as session:
        report = add_scale_data(session, SAMPLE_TODAY)
    database.dispose()
    assert report.people >= SCALE_PEOPLE
    assert report.projects >= SCALE_PROJECTS
    assert report.time_entries > 500_000
    return folder


@pytest.fixture(scope="module")
def settings(scale_template: Path) -> Settings:
    return _settings(scale_template)


@pytest.fixture(scope="module")
def anna(settings: Settings) -> Iterator[TestClient]:
    for client in start_client(create_app(settings)):
        assert login(client, "anna.claes", DEMO_PASSWORD).status_code == 200
        yield client


@pytest.fixture(scope="module")
def admin(settings: Settings) -> Iterator[TestClient]:
    for client in start_client(create_app(settings)):
        assert login(client, "admin", "admin-password-for-tests").status_code == 200
        yield client


def best_of(
    client: TestClient, method: str, url: str, limit: float, runs: int = 3, **kwargs: Any
) -> Any:
    """The answer of a request that must come within `limit` seconds (the best of a few tries)."""
    fastest = float("inf")
    response = None
    for _ in range(runs):
        started = time.perf_counter()
        response = client.request(method, url, **kwargs)
        fastest = min(fastest, time.perf_counter() - started)
        assert response.status_code == 200, (url, response.status_code, response.text[:300])
    assert fastest < limit, f"{method} {url} took {fastest:.3f}s (limit {limit}s)"
    assert response is not None
    return response.json() if "json" in response.headers.get("content-type", "") else response


# ---------------------------------------------------------------- the data set


def test_the_data_set_has_the_size_of_the_budgets(settings: Settings) -> None:
    database = Database(settings.resolved_database_url)
    with database.session() as session:
        people = session.scalar(select(func.count()).select_from(User)) or 0
        projects = session.scalar(select(func.count()).select_from(Project)) or 0
        entries = session.scalar(select(func.count()).select_from(TimeEntry)) or 0
    database.dispose()
    assert people >= SCALE_PEOPLE
    assert projects >= SCALE_PROJECTS
    assert entries > 500_000


# ---------------------------------------------------------------- projects


def test_the_project_list_and_its_counts_within_300_ms(anna: TestClient) -> None:
    first = best_of(anna, "GET", "/api/projects", 0.3)
    assert first["total"] > 4_000
    assert len(first["items"]) == 50
    best_of(anna, "GET", "/api/projects/counts", 0.3)
    best_of(anna, "GET", "/api/projects", 0.3, params={"after": first["next_after"]})
    best_of(anna, "GET", "/api/projects", 0.3, params={"status": "progress", "q": "sensor"})


def test_search_and_pickers_within_200_ms(anna: TestClient) -> None:
    best_of(anna, "GET", "/api/search/projects", 0.2, params={"q": "coating"})
    best_of(anna, "GET", "/api/search/projects", 0.2, params={"q": "20123"})
    best_of(anna, "GET", "/api/search/people", 0.2, params={"q": "an"})


def test_a_project_pages_calls_within_300_ms_each(anna: TestClient) -> None:
    number = 21_000
    for path in (
        f"/api/projects/{number}",
        f"/api/projects/{number}/log",
        f"/api/projects/{number}/remarks",
        f"/api/projects/{number}/tasks",
        f"/api/projects/{number}/planned-days",
        f"/api/projects/{number}/neighbours",
    ):
        best_of(anna, "GET", path, 0.3)


# ---------------------------------------------------------------- people planning


@pytest.mark.parametrize("mode", ["planned", "spent", "compare"])
def test_people_planning_of_the_root_within_1_5_seconds(admin: TestClient, mode: str) -> None:
    body = best_of(
        admin, "GET", "/api/people-planning", 1.5, params={"mode": mode, "period": "month"}
    )
    assert body["total_count"] >= SCALE_PEOPLE
    assert len(body["rows"]) >= SCALE_PEOPLE - body["hidden_count"]


def test_a_persons_drill_down_within_300_ms(admin: TestClient) -> None:
    person = admin.get("/api/people-planning", params={"q": "Anna Claes"}).json()["rows"][0]
    pid = person["person"]["id"]
    for mode in ("planned", "spent", "compare"):
        best_of(admin, "GET", f"/api/people-planning/{pid}", 0.3, params={"mode": mode})


# ---------------------------------------------------------------- timesheet, bootstrap, exports


def test_a_timesheet_save_within_150_ms(anna: TestClient) -> None:
    week = anna.get("/api/timesheet/2026-W41").json()
    line = next(line for line in week["lines"] if line["kind"] == "project")
    task = next(c["key"] for c in line["choices"] if c["name"] == "General")
    minutes = 60
    for _ in range(3):  # three different absolute values, so each is a real write
        started = time.perf_counter()
        response = anna.put(
            "/api/timesheet/2026-W41/cells",
            json={"day": "2026-10-08", "line": line["key"], "task": task, "minutes": minutes},
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 200, response.text
        assert elapsed < 0.15, f"a save took {elapsed:.3f}s"
        minutes += 60


def test_the_bootstrap_stays_under_300_kb_compressed(admin: TestClient) -> None:
    raw = admin.get("/api/bootstrap", headers={"Accept-Encoding": "identity"}).content
    assert len(gzip.compress(raw)) < 300_000


def test_a_period_of_booked_time_exports_in_reasonable_time(admin: TestClient) -> None:
    response = admin.get(
        "/api/exports/time-entries", params={"start": "2026-07-01", "end": "2026-09-30"}
    )
    assert response.status_code == 200
    assert response.content.count(b"\n") > 50_000


def test_responses_over_1_kb_are_compressed(anna: TestClient) -> None:
    response = anna.get("/api/projects", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
