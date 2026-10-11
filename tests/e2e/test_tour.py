"""A tour of every screen under the Content Security Policy, and the keyboard paths of the main
interactions. A CSP violation, a failed module or any script error is a console error here.
[§8.3] [§8.4] [SH-5]"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in

SCREENS = [
    ("projects", ".table__link"),
    ("projects?status=progress&q=sensor", ".table__link"),
    ("projects/4102", ".project-title"),
    ("projects/4102/planning", ".project-title"),
    ("projects/4102/people", ".project-title"),
    ("projects/4102/remarks", ".remark"),
    ("projects/4102/logbook", ".log-entry"),
    ("projects/4102/details", ".project-title"),
    ("timesheet", ".ts-card"),
    ("timesheet/2026-W40", ".ts-card"),
    ("people", ".pp-person"),
    ("people?mode=spent&period=month", ".pp-person"),
    ("people?mode=compare&period=year", ".pp-person"),
    ("plans", ".plan-project"),
    ("plans?project=4102", ".plan-summary"),
    ("profile", ".admin-card"),
    ("projects/999999", ".placeholder"),
]
ADMIN_SCREENS = [
    ("admin/org", ".org-row"),
    ("admin/people", ".admin-person"),
    ("admin/roles", ".admin-role-head"),
    ("admin/access", ".admin-assignments"),
    ("admin/sso", ".admin-assignments"),
    ("admin/audit", ".admin-table"),
]


@pytest.mark.parametrize(("look", "mode"), [("playful", "light"), ("boring", "dark")])
def test_every_screen_loads_without_console_errors(
    sample_server: str, page: Page, console_errors: list[str], look: str, mode: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}projects")
    sign_in(page, "anna.claes")
    for path, ready in SCREENS:
        page.goto(f"{sample_server}{path}")
        expect(page.locator(ready).first).to_be_visible()
    assert console_errors == [], console_errors


def test_every_administration_screen_loads_without_console_errors(
    sample_server: str, page: Page, console_errors: list[str]
) -> None:
    remember(page)
    page.goto(f"{sample_server}admin")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    for path, ready in ADMIN_SCREENS:
        page.goto(f"{sample_server}{path}")
        expect(page.locator(ready).first).to_be_visible()
    assert console_errors == [], console_errors


# ---------------------------------------------------------------- the keyboard


def test_the_page_can_be_used_by_keyboard_alone_from_the_menu_to_a_dialog(
    sample_server: str, page: Page
) -> None:
    """[§8.4] Skip link, search shortcut, menus, dialogs: all with keys; focus stays visible."""
    remember(page)
    page.goto(f"{sample_server}projects")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.locator(".table__link").first).to_be_visible()

    page.keyboard.press("Control+k")
    expect(page.get_by_role("searchbox")).to_be_focused()
    page.keyboard.press("Escape")

    page.get_by_role("button", name="+ New project").focus()
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="New project")
    expect(dialog).to_be_visible()
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.closest('[role=dialog]') !== null")
    assert focused  # focus stays inside the dialog
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)

    # a menu: open with Enter, choose with the keyboard, close with Escape
    page.get_by_role("button", name=re.compile(r"^Inside ")).focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("menu")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("menu")).to_have_count(0)


def test_the_status_of_a_project_is_changed_with_the_keyboard(
    sample_server: str, page: Page
) -> None:
    remember(page)
    page.goto(f"{sample_server}projects/4102")
    sign_in(page, "tomas.rivera")
    pill = page.locator(".badges .status-pill")
    expect(pill).to_contain_text("In progress")
    pill.focus()
    page.keyboard.press("Enter")
    item = page.get_by_role("menuitemradio", name="On hold")
    item.focus()
    page.keyboard.press("Enter")
    expect(pill).to_contain_text("On hold")


def test_the_timesheet_can_be_booked_with_the_keyboard(sample_server: str, page: Page) -> None:
    remember(page)
    page.goto(f"{sample_server}timesheet")
    sign_in(page, "anna.claes")
    card = page.locator(".ts-card").filter(has_text="Sensor retrofit")
    expect(card).to_be_visible()
    plus = card.get_by_role("button", name=re.compile("^Add "))
    plus.focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Space")
    expect(card.locator(".ts-card__hours")).to_have_text("2")
