"""Single sign-on in a real browser: the OpenID Connect round trip through a fake provider's sign-in
page, and Windows sign-in answered by Chromium through SSPI (Windows only). [AUTH-3]"""

import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
from playwright.sync_api import BrowserType, Page, expect
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from momato.config import Settings, UnknownUserPolicy
from momato.db.models import OrgNode, Role, RoleAssignment, User
from momato.db.models.people import UserKind
from momato.db.session import Database
from momato.domain.access import Scope
from momato.identity.providers import IdentityProviders
from momato.web import create_app
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, serve, sign_in
from tests.fake_idp import FakeIdentityProvider, fake_oidc_provider

# ---------------------------------------------------------------- OpenID Connect


@pytest.fixture
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


@pytest.fixture
def sign_in_as(idp: FakeIdentityProvider) -> Iterator[dict[str, object]]:
    """The provider's sign-in page; tests fill in the claims of the person who signs in there."""
    claims: dict[str, object] = {}

    async def authorize(request: Request) -> RedirectResponse:
        answer = idp.approve(str(request.url), **claims)
        callback = request.query_params["redirect_uri"]
        return RedirectResponse(f"{callback}?{urlencode(answer)}", status_code=302)

    with contextmanager(serve)(Starlette(routes=[Route("/authorize", authorize)])) as base:
        idp.authorization_endpoint = f"{base}authorize"
        yield claims


@pytest.fixture
def sso_server(
    sample_settings: Settings,
    sample_database: Database,
    idp: FakeIdentityProvider,
    sign_in_as: dict[str, object],
) -> Iterator[str]:
    del sign_in_as  # the sign-in page must be up before the app reads the provider's metadata
    with sample_database.session(write=True) as session:
        coatings = session.scalars(select(OrgNode.id).where(OrgNode.name == "Coatings")).one()
        jan = User(
            kind=UserKind.PERSON,
            name="Jan Peeters",
            username="jan.peeters",
            email="jan.peeters@example.com",
            org_node_id=coatings,
        )
        session.add(jan)
        session.flush()
        assignment = RoleAssignment(
            user_id=jan.id,
            role_id=session.scalars(select(Role.id).where(Role.key == "project_admin")).one(),
        )
        assignment.scope = Scope.node(coatings)
        session.add(assignment)
    providers = IdentityProviders(redirect={"entra": fake_oidc_provider(idp)})
    yield from serve(create_app(sample_settings, providers=providers))


def test_sign_in_with_microsoft_returns_to_the_same_page(
    sso_server: str, sign_in_as: dict[str, object], page: Page, console_errors: list[str]
) -> None:
    sign_in_as.update(oid="oid-jan", email="jan.peeters@example.com", name="J. Peeters (Quality)")
    remember(page)
    page.goto(f"{sso_server}projects/4102")
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_role("link", name="Sign in with Microsoft").click()
    expect(page).to_have_url(f"{sso_server}projects/4102")
    # The prepared person (matched on email) keeps the name the administrator gave them.
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    expect(page.get_by_role("button", name="Appearance and account of Jan Peeters")).to_be_visible()
    assert console_errors == []


def test_a_refused_sign_in_is_explained_and_the_address_tidied(
    sso_server: str, sign_in_as: dict[str, object], page: Page
) -> None:
    sign_in_as.update(oid="oid-stranger", email="stranger@example.com")
    remember(page)
    page.goto(f"{sso_server}projects")
    page.get_by_role("link", name="Sign in with Microsoft").click()
    dialog = page.get_by_role("dialog", name="Log in")
    expect(dialog.get_by_role("alert")).to_contain_text("no account has been set up for you")
    expect(page).to_have_url(f"{sso_server}projects")  # the error parameter is tidied away
    # the password sign-in still works next to it
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.locator(".table__link").first).to_be_visible()


# ---------------------------------------------------------------- Windows sign-in (SSPI)

ACCOUNT_BUTTON = re.compile(r"^Appearance and account of")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows SSPI")


def serve_windows(settings: Settings, **overrides: object) -> Iterator[str]:
    # Whoever runs the tests has no account here: let the first sign-in create one.
    settings = settings.model_copy(
        update={"windows_auth": True, "sso_unknown_users": UnknownUserPolicy.CREATE} | overrides
    )
    yield from serve(create_app(settings))  # the provider comes from the settings: real SSPI


@pytest.fixture
def windows_server(sample_settings: Settings, sample_database: Database) -> Iterator[str]:
    del sample_database  # loaded before the server starts
    yield from serve_windows(sample_settings)


@pytest.fixture
def windows_page(
    browser_type: BrowserType, browser_type_launch_args: dict[str, Any], tmp_path: Path
) -> Iterator[Page]:
    """A page in a browser that signs in to 127.0.0.1 with the Windows login, as an intranet
    zone or the AuthServerAllowlist policy arranges for real users.

    Chromium never does that from the incognito-like contexts Playwright normally uses, hence a
    browser with a profile of its own.
    """
    context = browser_type.launch_persistent_context(
        tmp_path / "profile",
        **{**browser_type_launch_args, "args": ["--auth-server-allowlist=127.0.0.1"]},
    )
    context.set_default_timeout(10_000)
    yield context.pages[0] if context.pages else context.new_page()
    context.close()


@windows_only
def test_a_visitor_is_signed_in_without_doing_anything(
    windows_server: str, windows_page: Page
) -> None:
    page = windows_page
    remember(page)
    page.goto(f"{windows_server}projects/4102")
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    expect(page).to_have_url(f"{windows_server}projects/4102")  # no redirects: the page stayed put
    page.get_by_role("button", name=ACCOUNT_BUTTON).click()
    expect(page.get_by_role("button", name="Log out")).to_be_visible()


@windows_only
def test_logging_out_lasts_and_the_admin_account_still_works(
    windows_server: str, windows_page: Page
) -> None:
    page = windows_page
    remember(page)
    page.goto(f"{windows_server}projects")
    expect(page.locator(".table__link").first).to_be_visible()
    page.get_by_role("button", name=ACCOUNT_BUTTON).click()
    page.get_by_role("button", name="Log out").click()
    dialog = page.get_by_role("dialog", name="Log in")
    expect(dialog).to_be_visible()
    page.reload()  # not signed in again behind the person's back
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()

    sign_in(page, "admin", TEST_ADMIN_PASSWORD)  # the break-glass account
    expect(page.locator(".table__link").first).to_be_visible()


@windows_only
def test_with_automatic_sign_in_off_it_takes_a_click(
    sample_settings: Settings, sample_database: Database, windows_page: Page
) -> None:
    del sample_database
    page = windows_page
    remember(page)
    for base in serve_windows(sample_settings, windows_auth_automatic=False):
        page.goto(f"{base}projects")
        dialog = page.get_by_role("dialog", name="Log in")
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="Sign in with Windows").click()
        expect(page.locator(".table__link").first).to_be_visible()


@windows_only
def test_a_browser_that_does_not_answer_leaves_the_visitor_at_the_login(
    windows_server: str, page: Page, console_errors: list[str]
) -> None:
    """Playwright's ordinary (incognito-like) page: Chromium keeps the Windows login to itself."""
    remember(page)
    page.goto(f"{windows_server}projects")
    dialog = page.get_by_role("dialog", name="Log in")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Sign in with Windows").click()
    expect(dialog.get_by_role("alert")).to_contain_text("did not work in this browser")
    assert console_errors == []
