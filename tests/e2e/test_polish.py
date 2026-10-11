"""The details that make it feel right, in a real browser: edits that show at once and roll back,
tabular numerals, motion that follows the visitor's preference. [SH-10] [TS-14] [APP-5]"""

import re
import time

from playwright.sync_api import Page, Route, expect

from tests.e2e.conftest import remember, sign_in

SENSORS = 4102


def open_project(page: Page, base: str) -> None:
    remember(page)
    page.goto(f"{base}projects/{SENSORS}")
    sign_in(page, "tomas.rivera")
    expect(page.locator(".project-title")).to_be_visible()


# ---------------------------------------------------------------- SH-10: optimistic edits


def test_an_edit_shows_at_once_even_while_the_server_is_slow(
    sample_server: str, page: Page
) -> None:
    """[SH-10] The status changes on screen before the server has answered."""
    open_project(page, sample_server)
    held: list[Route] = []
    page.route(
        re.compile(rf"/api/projects/{SENSORS}$"),
        lambda route: held.append(route) if route.request.method == "PATCH" else route.continue_(),
    )
    page.locator(".badges .status-pill").click()
    page.get_by_role("menuitemradio", name="On hold").click()
    expect(page.locator(".badges .status-pill")).to_contain_text("On hold")  # nothing answered yet
    deadline = time.monotonic() + 5
    while not held and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert len(held) == 1  # the request is waiting: the screen did not
    held[0].continue_()
    expect(page.locator(".badges .status-pill")).to_contain_text("On hold")


def test_a_refused_edit_rolls_back_with_a_message(sample_server: str, page: Page) -> None:
    """[SH-10]"""
    open_project(page, sample_server)
    page.route(
        re.compile(rf"/api/projects/{SENSORS}$"),
        lambda route: (
            route.fulfill(
                status=422,
                content_type="application/json",
                body='{"error": "rule_violation", "message": "the end date comes before the start"}',
            )
            if route.request.method == "PATCH"
            else route.continue_()
        ),
    )
    expect(page.locator(".badges .status-pill")).to_contain_text("In progress")
    page.locator(".badges .status-pill").click()
    page.get_by_role("menuitemradio", name="On hold").click()
    expect(page.get_by_role("status")).to_contain_text("the end date comes before the start")
    expect(page.locator(".badges .status-pill")).to_contain_text("In progress")


# ---------------------------------------------------------------- TS-14: tabular numerals


def test_timesheet_numbers_use_tabular_numerals(sample_server: str, page: Page) -> None:
    """[TS-14]"""
    remember(page)
    page.goto(f"{sample_server}timesheet")
    sign_in(page, "anna.claes")
    expect(page.locator(".ts-card").first).to_be_visible()
    for selector in (
        ".ts-card__hours",
        ".ts-card__week",
        ".ts-ring__hours",
        ".week-card",
    ):
        variant = page.locator(selector).first.evaluate(
            "el => getComputedStyle(el).fontVariantNumeric"
        )
        assert "tabular-nums" in variant, (selector, variant)


# ---------------------------------------------------------------- APP-5: motion


def transition_of(page: Page, selector: str) -> str:
    return page.locator(selector).first.evaluate("el => getComputedStyle(el).transitionDuration")


def test_motion_is_as_designed_and_off_when_the_visitor_asks(
    sample_server: str, page: Page
) -> None:
    """[APP-5] Hover transitions are about .12 s; with reduced motion they are all but gone."""
    remember(page)
    page.goto(f"{sample_server}projects")
    sign_in(page, "anna.claes")
    expect(page.locator(".table__link").first).to_be_visible()
    assert transition_of(page, ".btn") != "0s"
    assert "0.12s" in transition_of(page, ".btn")

    page.emulate_media(reduced_motion="reduce")
    assert transition_of(page, ".btn") == "0.001s"
    animation = page.locator(".btn").first.evaluate("el => getComputedStyle(el).animationDuration")
    assert animation in {"0.001s", "0s"}
