"""The scale data set in a real browser: 5,000 projects, 500 people (§8.5). Run with `-m scale`.

Time is measured from the click that asks for a screen to the moment its content is visible. The
limits are the budgets of REQUIREMENTS 8.5 with room for the browser itself. [§8.5] [D-028]
"""

import re
import time
from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, expect

from momato.config import Settings
from momato.web import create_app
from tests.api.test_scale import scale_template  # noqa: F401  (the fixture, built once per run)
from tests.conftest import DEMO_PASSWORD, _settings
from tests.e2e.conftest import remember, serve, sign_in

pytestmark = pytest.mark.scale


@pytest.fixture(scope="module")
def scale_server(scale_template) -> Iterator[str]:  # noqa: F811
    settings: Settings = _settings(scale_template)
    yield from serve(create_app(settings))


def timed(page: Page, action, ready, limit: float, what: str) -> None:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    action()
    expect(ready).to_be_visible(timeout=int(limit * 1000) + 5000)
    elapsed = time.perf_counter() - started
    assert elapsed < limit, f"{what} took {elapsed:.2f}s (limit {limit}s)"


def test_the_project_list_renders_within_500_ms(scale_server: str, page: Page) -> None:
    remember(page)
    page.goto(f"{scale_server}timesheet")
    sign_in(page, "anna.claes", DEMO_PASSWORD)
    expect(page.locator(".ts-card").first).to_be_visible()
    timed(
        page,
        lambda: page.get_by_role("link", name="Projects").first.click(),
        page.locator(".table__link").first,
        1.0,  # the budget (500 ms) plus the browser's own overhead
        "the project list",
    )
    expect(page.locator(".list-count")).to_contain_text("projects")
    match = re.match(r"[\d,]+", page.locator(".list-count").inner_text())
    assert match is not None
    count = int(match.group(0).replace(",", ""))
    assert count > 4_000


def test_a_project_page_opens_quickly(scale_server: str, page: Page) -> None:
    remember(page)
    page.goto(f"{scale_server}projects")
    sign_in(page, "anna.claes", DEMO_PASSWORD)
    expect(page.locator(".table__link").first).to_be_visible()
    timed(
        page,
        lambda: page.locator(".table__link").first.click(),
        page.locator(".project-title"),
        1.5,
        "a project page",
    )


def test_people_planning_of_the_root_renders_within_a_few_seconds(
    scale_server: str, page: Page
) -> None:
    remember(page)
    page.goto(f"{scale_server}projects")
    sign_in(page, "anna.claes", DEMO_PASSWORD)
    expect(page.locator(".table__link").first).to_be_visible()
    timed(
        page,
        lambda: page.get_by_role("link", name="People planning").click(),
        page.locator(".pp-person").first,
        3.0,  # the budget (1.5 s for the answer) plus rendering five hundred rows
        "people planning",
    )
    expect(page.locator(".list-count")).to_contain_text("people")
