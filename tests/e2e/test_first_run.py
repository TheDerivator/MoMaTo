"""A fresh installation in a real browser: the administrator names the organisation, then the app
opens; anyone else is told it is not set up yet. [ADM-1] [SH-12]"""

from collections.abc import Callable

from playwright.sync_api import Page, expect

from momato.db.session import Database
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in
from tests.factories import make_user


def test_the_administrator_names_the_organisation_and_the_app_opens(
    live_server: str,
    page: Page,
    console_errors: list[str],
    assert_accessible: Callable[[str], None],
) -> None:
    remember(page)
    page.goto(live_server)
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)

    heading = page.get_by_role("heading", name="Set up your organisation")
    expect(heading).to_be_visible()  # not a blank page: the tree has no root yet
    assert_accessible("the set-up page")
    create = page.get_by_role("button", name="Create the organisation")
    expect(create).to_be_disabled()
    page.get_by_label("Name of the organisation").fill("Acme Corp")
    create.click()

    expect(heading).to_be_hidden()
    expect(page.locator(".toast").filter(has_text="Organisation created")).to_be_visible()
    expect(page.locator(".tree-pane").get_by_text("Acme Corp").first).to_be_visible()

    page.goto(f"{live_server}admin/org")  # the root is there to build on
    expect(page.get_by_label("Name of Acme Corp")).to_have_value("Acme Corp")
    page.reload()
    expect(page.get_by_label("Name of Acme Corp")).to_be_visible()  # and it persisted
    assert console_errors == []


def test_anyone_else_is_told_the_installation_is_not_set_up_yet(
    live_server: str, page: Page, database: Database, console_errors: list[str]
) -> None:
    with database.session(write=True) as session:
        make_user(session, "Pat Plain", username="pat", password="a-long-password-1")
    remember(page)
    page.goto(live_server)
    sign_in(page, "pat", "a-long-password-1")

    expect(page.get_by_role("heading", name="Not set up yet")).to_be_visible()
    expect(page.get_by_role("button", name="Create the organisation")).to_have_count(0)
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    assert console_errors == []
