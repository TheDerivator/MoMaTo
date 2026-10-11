"""axe-core (WCAG 2.1 AA) on every screen, its popovers and dialogs, in all four appearances.
[APP-4] [PL-1] [PL-2] [PL-5] [PL-8] [SH-5] [SH-7] [AP-2] [AP-3] [AP-5] [AP-6]"""

import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in

APPEARANCES = [
    pytest.param(mode, look, id=f"{mode}-{look}")
    for mode in ("light", "dark")
    for look in ("playful", "boring")
]


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_login_dialog_is_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(sample_server)
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    assert_accessible(f"the login dialog ({mode}, {look})")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_project_list_and_its_popovers_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(sample_server)
    sign_in(page, "anna.claes")
    expect(page.locator(".table__link").first).to_be_visible()
    where = f"({mode}, {look})"

    assert_accessible(f"the project list {where}")

    page.get_by_role("button", name=re.compile(r"^In progress")).click()
    expect(page.get_by_role("button", name=re.compile(r"^In progress"))).to_have_attribute(
        "aria-pressed", "true"
    )
    assert_accessible(f"the project list with a status selected {where}")

    page.get_by_role("button", name="Inside Brightwater Industries").click()
    expect(page.get_by_role("menu")).to_be_visible()
    assert_accessible(f"the breadcrumb menu {where}")
    page.keyboard.press("Escape")
    expect(page.get_by_role("menu")).to_have_count(0)

    page.get_by_role("button", name=re.compile(r"^Appearance and account of")).click()
    expect(page.get_by_role("dialog", name="Appearance")).to_be_visible()
    assert_accessible(f"the appearance popover {where}")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog", name="Appearance")).to_have_count(0)


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_collapsed_panes_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look, tree=False)
    page.goto(sample_server)
    sign_in(page, "anna.claes")
    expect(page.locator(".table__link").first).to_be_visible()
    page.get_by_role("button", name="Collapse menu").click()
    expect(page.locator(".menu-rail")).to_be_visible()
    expect(page.locator(".tree-rail")).to_be_visible()
    assert_accessible(f"the rails ({mode}, {look})")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_new_project_dialog_and_its_picker_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(sample_server)
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="+ New project").click()
    dialog = page.get_by_role("dialog", name="New project")
    expect(dialog).to_be_visible()
    assert_accessible(f"the new project dialog ({mode}, {look})")

    dialog.get_by_label("Coordinator").fill("An")
    expect(dialog.get_by_role("listbox", name="Coordinator results")).to_be_visible()
    assert_accessible(f"the person picker with results ({mode}, {look})")


def test_the_not_found_page_is_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None]
) -> None:
    remember(page)
    page.goto(f"{sample_server}projects/999999")
    sign_in(page, "anna.claes")
    expect(page.get_by_role("heading", name="Not found or no access")).to_be_visible()
    assert_accessible("the not found page")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_project_page_tabs_and_their_popovers_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}projects/4102")
    sign_in(page, "tomas.rivera")  # the coordinator: every editing affordance is there
    expect(page.get_by_role("heading", name="Sensor retrofit on conveyor 4")).to_be_visible()
    where = f"({mode}, {look})"
    assert_accessible(f"the overview {where}")

    page.locator(".badges .status-pill").click()
    expect(page.get_by_role("menu", name="Status")).to_be_visible()
    assert_accessible(f"the status menu {where}")
    page.keyboard.press("Escape")

    page.get_by_role("button", name="+ Action plan").click()
    expect(page.get_by_role("menu", name="Action plans")).to_be_visible()
    assert_accessible(f"the action plan checklist {where}")
    page.keyboard.press("Escape")

    page.get_by_role("button", name="+ Add person").click()
    expect(page.get_by_role("dialog", name="Add a person")).to_be_visible()
    assert_accessible(f"the person search {where}")
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Remove Pieter Kools").click()
    expect(page.get_by_role("dialog", name="Remove Pieter Kools?")).to_be_visible()
    assert_accessible(f"the remove person confirmation {where}")
    page.keyboard.press("Escape")

    page.get_by_role("button", name=re.compile(r"^Goal:")).click()
    expect(page.get_by_label("Goal", exact=True)).to_be_focused()
    assert_accessible(f"the goal editor {where}")
    page.keyboard.press("Escape")

    for tab in ("Remarks", "Logbook", "All details", "Planning", "People & days"):
        page.get_by_role("navigation", name="Project sections").get_by_role(
            "link", name=re.compile(f"^{re.escape(tab)}")
        ).click()
        expect(page.get_by_role("link", name=re.compile(f"^{re.escape(tab)}"))).to_have_attribute(
            "aria-current", "page"
        )
        page.wait_for_load_state("networkidle")
        assert_accessible(f"the {tab} tab {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_remarks_in_all_their_states_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}projects/4102/remarks")
    sign_in(page, "anna.claes")
    cards = page.locator("article.remark")
    expect(cards.first).to_be_visible()
    where = f"({mode}, {look})"

    page.get_by_label("Write a remark").fill("**Bold** text with #4307")
    page.get_by_role("button", name="Preview").click()
    expect(page.locator(".composer__preview strong")).to_be_visible()
    assert_accessible(f"the composer preview {where}")
    page.get_by_role("button", name="Write", exact=True).click()

    cards.first.get_by_role("button", name="Reply").click()
    expect(cards.first.get_by_label("Write a reply")).to_be_focused()
    assert_accessible(f"a reply box {where}")
    page.keyboard.press("Escape")

    own = cards.filter(
        has=page.locator(".remark__main > .remark__who", has_text="Anna Claes")
    ).first
    own.get_by_role("button", name="Edit", exact=True).click()
    expect(page.get_by_label("Edit remark")).to_be_visible()
    assert_accessible(f"the remark editor {where}")
    page.keyboard.press("Escape")

    cards.first.locator(".md img").click()
    expect(page.get_by_role("dialog", name=re.compile("^Image"))).to_be_visible()
    assert_accessible(f"the lightbox {where}")
    page.keyboard.press("Escape")

    own.get_by_role("button", name="Delete", exact=True).click()
    expect(page.get_by_role("dialog", name="Delete this remark?")).to_be_visible()
    assert_accessible(f"the delete confirmation {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_task_dialog_and_the_day_cells_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}projects/4102/planning")
    sign_in(page, "tomas.rivera")
    where = f"({mode}, {look})"
    page.get_by_role("button", name="+ Add task").click()
    expect(page.get_by_role("dialog", name="Add task")).to_be_visible()
    assert_accessible(f"the add task dialog {where}")
    page.keyboard.press("Escape")

    page.locator(".gantt__name--button", has_text="Installation").click()
    expect(page.get_by_role("dialog", name="Edit task")).to_be_visible()
    assert_accessible(f"the edit task dialog {where}")
    page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Delete").click()
    expect(page.get_by_role("dialog", name="Delete this task?")).to_be_visible()
    assert_accessible(f"the delete task confirmation {where}")
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")

    page.get_by_role("navigation", name="Project sections").get_by_role(
        "link", name=re.compile("^People & days")
    ).click()
    cell = page.locator(".days-cell button").first
    cell.click()
    expect(page.locator(".days-cell__input")).to_be_focused()
    assert_accessible(f"a day cell being edited {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_timesheet_its_popover_and_the_celebration_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}timesheet")
    sign_in(page, "anna.claes")
    expect(page.locator(".ts-card").first).to_be_visible()
    where = f"({mode}, {look})"
    assert_accessible(f"the timesheet {where}")

    # a card with hours, and a card that has reached its plan, and the amber week card
    page.get_by_role("button", name=re.compile("^Add .* to Digital shift handover")).click(
        click_count=4
    )
    page.locator(".ts-day", has=page.locator("b", has_text="Mon")).click()
    for _ in range(8):
        page.get_by_role(
            "button", name=re.compile("^Remove .* from Vision-based quality check")
        ).click()
    assert_accessible(f"the timesheet with an open day {where}")

    page.get_by_role("button", name="+ Add project").click()
    expect(page.get_by_role("dialog", name="Add a project")).to_be_visible()
    assert_accessible(f"the add project popover {where}")
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Submit week").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    # axe reads colours as they are on screen: let the modal's pop-in finish first
    page.locator(".celebration__modal").evaluate(
        "el => Promise.all(el.getAnimations().map((a) => a.finished))"
    )
    assert_accessible(f"the celebration {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_people_planning_in_every_mode_is_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}people")
    sign_in(page, "anna.claes")
    expect(page.locator(".pp-person").first).to_be_visible()
    where = f"({mode}, {look})"
    assert_accessible(f"people planning, planned {where}")

    page.get_by_role("button", name=re.compile("Anna Claes: show projects")).click()
    expect(page.locator(".pp-line").first).to_be_visible()
    assert_accessible(f"people planning with a person open {where}")

    page.get_by_role("button", name="Spent").click()
    expect(page.get_by_role("button", name="Past week")).to_be_visible()
    expect(page.locator(".pp-line").first).to_be_visible()
    assert_accessible(f"people planning, spent {where}")

    page.get_by_role("button", name="Compare").click()
    page.get_by_role("button", name="Past year").click()
    expect(page.locator(".pp-head__bucket")).to_have_count(12)
    expect(page.locator(".pp-line").first).to_be_visible()
    assert_accessible(f"people planning, compare {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_action_plans_with_their_dialogs_and_menus_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}plans")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)  # a plan manager: every affordance is there
    expect(page.locator(".plan-project").first).to_be_visible()
    where = f"({mode}, {look})"
    assert_accessible(f"action plans {where}")

    page.locator(".plan-project__button").first.click()
    expect(page.locator(".plan-summary")).to_be_visible()
    assert_accessible(f"action plans with a project selected {where}")

    page.get_by_role("button", name="Plan actions").click()
    expect(page.get_by_role("menu", name="Plan actions")).to_be_visible()
    assert_accessible(f"the plan menu {where}")
    page.get_by_role("menuitem", name="Edit plan").click()
    expect(page.get_by_role("dialog", name="Edit plan")).to_be_visible()
    assert_accessible(f"the plan dialog {where}")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog", name="Edit plan")).to_have_count(0)

    page.get_by_role("button", name="+ Add project").click()
    expect(page.get_by_role("dialog", name="Add a project to this plan")).to_be_visible()
    assert_accessible(f"the add project search {where}")
    page.keyboard.press("Escape")

    page.locator(".tree-row").filter(has_text="Quality").first.click()
    expect(page.locator(".plan-empty")).to_be_visible()
    assert_accessible(f"action plans without a plan {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_administration_pages_and_the_profile_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}admin/org")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    where = f"({mode}, {look})"
    sections = [
        ("org", ".org-row", "the organisation tree"),
        ("people", ".admin-person", "the people list"),
        ("roles", ".admin-role-head", "the roles"),
        ("access", ".admin-assignments", "the default access"),
        ("sso", ".admin-assignments", "single sign-on"),
        ("audit", ".admin-table tbody tr", "the audit log"),
    ]
    for section, ready, what in sections:
        page.goto(f"{sample_server}admin/{section}")
        expect(page.locator(ready).first).to_be_visible()
        assert_accessible(f"{what} {where}")

    page.goto(f"{sample_server}admin/org")
    page.get_by_role("button", name="+ Branch").first.click()
    expect(page.locator(".org-row__add")).to_be_visible()
    assert_accessible(f"the add branch form {where}")

    page.goto(f"{sample_server}admin/people")
    expect(page.locator(".admin-person").first).to_be_visible()
    page.get_by_role("button", name="+ New person").click()
    expect(page.get_by_role("dialog", name="New person")).to_be_visible()
    assert_accessible(f"the new person dialog {where}")
    page.keyboard.press("Escape")

    page.get_by_role("link", name="Anna Claes").click()
    expect(page.get_by_role("region", name="Sign-in")).to_be_visible()
    assert_accessible(f"a person's page {where}")
    page.get_by_role("button", name="Generate a new password").click()
    expect(page.locator(".admin-secret__value")).to_be_visible()
    assert_accessible(f"a person's page with a new password {where}")

    page.goto(f"{sample_server}profile")
    expect(page.get_by_role("region", name="About you")).to_be_visible()
    assert_accessible(f"the profile of the administrator {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_the_profile_with_its_password_form_is_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}profile")
    sign_in(page, "anna.claes")
    expect(page.get_by_role("region", name="Change password")).to_be_visible()
    assert_accessible(f"the profile ({mode}, {look})")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_api_tokens_and_the_export_popovers_are_accessible(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}profile")
    sign_in(page, "tomas.rivera")
    where = f"({mode}, {look})"
    tokens = page.get_by_role("region", name="API tokens")
    expect(tokens).to_be_visible()
    assert_accessible(f"the profile without tokens {where}")

    tokens.get_by_role("button", name="New token").click()
    expect(page.get_by_role("dialog", name="New API token")).to_be_visible()
    assert_accessible(f"the new token dialog {where}")
    page.get_by_label("Name").fill("Claude Code")
    page.get_by_role("button", name="Create token").click()
    expect(page.get_by_role("dialog", name="Your new token")).to_be_visible()
    assert_accessible(f"the new token's secret {where}")
    page.get_by_role("button", name="Done").click()
    expect(tokens.get_by_role("row", name=re.compile("Claude Code"))).to_be_visible()
    assert_accessible(f"the profile with a token {where}")

    page.goto(f"{sample_server}projects")
    expect(page.locator(".table__link").first).to_be_visible()
    page.get_by_role("button", name="Export").click()
    expect(page.get_by_role("dialog", name="Export the project list")).to_be_visible()
    assert_accessible(f"the project export {where}")

    page.goto(f"{sample_server}people?mode=spent&period=week")
    expect(page.locator(".pp-person").first).to_be_visible()
    page.get_by_role("button", name="Export time").click()
    expect(page.get_by_role("dialog", name="Export booked time")).to_be_visible()
    assert_accessible(f"the time export {where}")
    page.get_by_role("dialog", name="Export booked time").get_by_label("To").fill("2026-09-01")
    expect(page.get_by_role("alert")).to_be_visible()
    assert_accessible(f"the time export with a wrong period {where}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES)
def test_what_a_token_wrote_is_accessible_with_its_via_marks(
    sample_server: str, page: Page, assert_accessible: Callable[[str], None], mode: str, look: str
) -> None:
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}profile")
    sign_in(page, "tomas.rivera")
    page.get_by_role("button", name="New token").click()
    page.get_by_label("Name").fill("Claude Code")
    page.get_by_label(re.compile("Read and write")).check()
    page.get_by_role("button", name="Create token").click()
    secret = page.get_by_test_id("token-secret").inner_text()
    page.get_by_role("button", name="Done").click()
    response = page.request.post(
        f"{sample_server}api/projects/4102/remarks",
        headers={"Authorization": f"Bearer {secret}"},
        data={"body_md": "Written through a token."},
    )
    assert response.ok
    page.goto(f"{sample_server}projects/4102/remarks")
    expect(page.locator(".via-badge").first).to_be_visible()
    assert_accessible(f"remarks with a via mark ({mode}, {look})")
