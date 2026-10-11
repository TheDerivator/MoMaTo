"""The page loads in a real browser: nothing from another origin, no errors, CSP enforced. [SH-8]"""

from collections.abc import Callable

from playwright.sync_api import Page, expect


def test_the_login_page_loads_without_contacting_another_origin(
    live_server: str,
    page: Page,
    console_errors: list[str],
    foreign_requests: list[str],
    assert_accessible: Callable[[str], None],
) -> None:
    page.goto(live_server)
    expect(page).to_have_title("Projects · MoMaTo")
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()  # a visitor must sign in
    assert foreign_requests == []
    assert console_errors == []
    assert_accessible("the login dialog")


def test_an_app_route_loads_the_same_page(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/4102/planning")
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()


def test_the_browser_enforces_the_content_security_policy(live_server: str, page: Page) -> None:
    """An inline script (what an injected one would be) does not run; the page's own module does."""
    page.goto(live_server)
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()  # the module script ran
    ran = page.evaluate(
        """() => {
            const script = document.createElement("script");
            script.textContent = "window.__injected = true";
            document.head.append(script);
            return window.__injected === true;
        }"""
    )
    assert ran is False


def test_inline_styles_in_markup_are_blocked(live_server: str, page: Page) -> None:
    page.goto(live_server)
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    applied = page.evaluate(
        """() => {
            const box = document.createElement("div");
            box.setAttribute("style", "position: fixed; top: 0; width: 333px");
            document.body.append(box);
            return getComputedStyle(box).width === "333px";
        }"""
    )
    assert applied is False


def test_the_favicon_is_served(live_server: str, page: Page) -> None:
    response = page.request.get(f"{live_server}static/img/favicon.svg")
    assert response.ok
    assert "image/svg+xml" in response.headers["content-type"]
