"""The shell in a real browser: appearance, remembered states, measurements, narrow screens.
[SH-1] [SH-2] [SH-3] [SH-6] [SH-7] [SH-9] [APP-1] [APP-2] [APP-3]"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import remember, sign_in

LOOKS = ("playful", "boring")


def open_app(page: Page, base: str, *, path: str = "projects") -> None:
    page.goto(f"{base}{path}")
    sign_in(page, "anna.claes")
    expect(page.locator(".table__link").first).to_be_visible()


def open_appearance(page: Page) -> None:
    page.get_by_role("button", name=re.compile(r"^Appearance and account of")).click()
    expect(page.get_by_role("dialog", name="Appearance")).to_be_visible()


def root_attribute(page: Page, name: str) -> str | None:
    return page.evaluate(f"document.documentElement.getAttribute('data-{name}')")


def width_of(page: Page, selector: str) -> float:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{selector} is not shown"
    return box["width"]


def style_of(page: Page, selector: str, prop: str) -> str:
    return page.locator(selector).first.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)


# ---------------------------------------------------------------- appearance


def test_the_mode_follows_the_operating_system_until_one_is_chosen(
    sample_server: str, page: Page
) -> None:
    remember(page)
    page.emulate_media(color_scheme="light")
    open_app(page, sample_server)
    assert root_attribute(page, "mode") == "light"

    page.emulate_media(color_scheme="dark")  # the OS changes: so does the app
    expect(page.locator("html")).to_have_attribute("data-mode", "dark")

    open_appearance(page)
    page.get_by_role("group", name="Mode").get_by_role("button", name="Light").click()
    expect(page.locator("html")).to_have_attribute("data-mode", "light")
    page.emulate_media(color_scheme="light")
    page.emulate_media(color_scheme="dark")  # a chosen mode is no longer overridden
    expect(page.locator("html")).to_have_attribute("data-mode", "light")


def test_mode_and_style_survive_a_reload(sample_server: str, page: Page) -> None:
    remember(page)
    open_app(page, sample_server)
    assert root_attribute(page, "look") == "playful"
    open_appearance(page)
    page.get_by_role("group", name="Mode").get_by_role("button", name="Dark").click()
    page.get_by_role("group", name="Style").get_by_role("button", name="Boring").click()
    expect(page.locator("html")).to_have_attribute("data-look", "boring")

    page.reload()
    expect(page.locator(".table__link").first).to_be_visible()
    assert root_attribute(page, "mode") == "dark"
    assert root_attribute(page, "look") == "boring"
    open_appearance(page)
    expect(
        page.get_by_role("group", name="Mode").get_by_role("button", name="Dark")
    ).to_have_attribute("aria-pressed", "true")
    expect(
        page.get_by_role("group", name="Style").get_by_role("button", name="Boring")
    ).to_have_attribute("aria-pressed", "true")


def test_the_stored_appearance_is_applied_before_the_app_runs(
    sample_server: str, page: Page
) -> None:
    remember(page, mode="dark", look="boring")
    page.goto(sample_server)
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    assert root_attribute(page, "mode") == "dark"  # even on the login dialog
    assert root_attribute(page, "look") == "boring"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != "rgb(255, 255, 255)"


def test_the_celebration_switch_is_remembered(sample_server: str, page: Page) -> None:
    remember(page)
    open_app(page, sample_server)
    open_appearance(page)
    switch = page.get_by_label("Celebrate submitted weeks")
    expect(switch).to_be_checked()
    switch.uncheck()
    page.reload()
    expect(page.locator(".table__link").first).to_be_visible()
    open_appearance(page)
    expect(page.get_by_label("Celebrate submitted weeks")).not_to_be_checked()


# ---------------------------------------------------------------- collapse states


def test_the_tree_pane_is_collapsed_by_default_and_remembers_what_the_user_chose(
    sample_server: str, page: Page
) -> None:
    page.goto(sample_server)  # nothing stored: the defaults
    sign_in(page, "anna.claes")
    expect(page.locator(".tree-rail")).to_be_visible()
    expect(page.locator(".tree-pane")).to_have_count(0)
    expect(page.locator(".tree-rail__name")).to_have_text("Brightwater Industries")

    page.get_by_role("button", name="Show organisation").click()
    expect(page.locator(".tree-pane")).to_be_visible()
    page.reload()
    expect(page.locator(".tree-pane")).to_be_visible()

    page.get_by_role("button", name="Collapse organisation pane").click()
    page.reload()
    expect(page.locator(".tree-rail")).to_be_visible()


def test_the_main_menu_collapses_to_a_rail_and_remembers_it(sample_server: str, page: Page) -> None:
    remember(page)
    open_app(page, sample_server)
    expect(page.locator(".menu")).to_be_visible()
    page.get_by_role("button", name="Collapse menu").click()
    expect(page.locator(".menu-rail")).to_be_visible()
    page.reload()
    expect(page.locator(".menu-rail")).to_be_visible()
    # icon buttons keep their names
    expect(page.locator(".menu-rail").get_by_role("link", name="People planning")).to_be_visible()
    page.get_by_role("button", name="Expand menu").first.click()
    expect(page.locator(".menu")).to_be_visible()


def test_the_main_menu_lists_the_four_views_in_order(sample_server: str, page: Page) -> None:
    remember(page)
    open_app(page, sample_server)
    items = page.locator(".menu .nav__item")
    expect(items).to_have_text(["Projects", "Action plans", "People planning", "My timesheet"])
    expect(items.first).to_have_attribute("aria-current", "page")
    expect(page.locator(".topbar__date")).to_have_text("Thursday 8 October 2026")


# ---------------------------------------------------------------- measurements


def test_the_panes_have_the_designed_widths(sample_server: str, page: Page) -> None:
    remember(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, sample_server)
    assert width_of(page, ".tree-pane") == 236
    assert width_of(page, ".menu") == 228
    page.get_by_role("button", name="Collapse organisation pane").click()
    page.get_by_role("button", name="Collapse menu").click()
    assert width_of(page, ".tree-rail") == 48
    assert width_of(page, ".menu-rail") == 64


@pytest.mark.parametrize(
    ("look", "radius", "display_font", "body_font"),
    [
        ("playful", "20px", "Bricolage Grotesque", "Figtree"),
        ("boring", "6px", "IBM Plex Sans", "IBM Plex Sans"),
    ],
)
def test_the_style_sets_the_corner_radius_and_the_fonts(
    sample_server: str, page: Page, look: str, radius: str, display_font: str, body_font: str
) -> None:
    remember(page, look=look)
    open_app(page, sample_server)
    assert style_of(page, ".table-card", "borderTopLeftRadius") == radius
    assert display_font in style_of(page, ".crumbs__title", "fontFamily")
    assert body_font in style_of(page, ".table__name", "fontFamily")
    assert page.evaluate("document.fonts.check('16px \"" + display_font + "\"')")  # actually loaded


def test_numbers_use_tabular_figures(sample_server: str, page: Page) -> None:
    remember(page)
    open_app(page, sample_server)
    assert "tabular-nums" in style_of(page, ".table__number", "fontVariantNumeric")
    assert "tabular-nums" in style_of(page, ".list-count", "fontVariantNumeric")


# ---------------------------------------------------------------- narrow screens


def test_below_720_px_both_panes_are_rails_and_only_the_table_scrolls(
    sample_server: str, page: Page
) -> None:
    remember(page)  # the tree is stored as expanded: narrow screens override that
    page.set_viewport_size({"width": 390, "height": 800})
    open_app(page, sample_server)
    expect(page.locator(".tree-pane")).to_have_count(0)
    expect(page.locator(".menu")).to_have_count(0)
    expect(page.locator(".tree-rail")).to_be_visible()
    expect(page.locator(".menu-rail")).to_be_visible()

    page_scrolls = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert page_scrolls is False
    card_scrolls = page.locator(".table-card").evaluate("el => el.scrollWidth > el.clientWidth")
    assert card_scrolls is True


def test_a_wide_screen_keeps_the_panes_as_the_user_left_them(
    sample_server: str, page: Page
) -> None:
    remember(page)
    page.set_viewport_size({"width": 390, "height": 800})
    open_app(page, sample_server)
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(page.locator(".tree-pane")).to_be_visible()
    expect(page.locator(".menu")).to_be_visible()


def test_a_rail_opens_its_pane_over_a_narrow_page(sample_server: str, page: Page) -> None:
    remember(page)
    page.set_viewport_size({"width": 390, "height": 800})
    open_app(page, sample_server)

    page.get_by_role("button", name="Show organisation").click()
    expect(page.locator(".tree-pane")).to_be_visible()
    page.locator(".tree-row").filter(has_text="Logistics").click()
    expect(page).to_have_url(re.compile(r"node=\d+"))
    expect(page.locator(".tree-pane")).to_have_count(0)  # choosing closes it

    page.locator(".menu-rail__logo").click()
    expect(page.locator(".menu")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".menu")).to_have_count(0)

    page.locator(".menu-rail__logo").click()
    page.locator(".pane-backdrop").click(position={"x": 380, "y": 400})
    expect(page.locator(".menu")).to_have_count(0)
