"""The Projects list in a real browser: paging, filters, counts, creating. [PL-1] [PL-2] [PL-3]
[PL-4] [PL-5] [PL-6] [PL-7] [PL-8] [SH-3] [SH-4] [SH-5] [SH-12]"""

import re

import httpx2
from playwright.sync_api import Locator, Page, expect

from momato.services.sample_data import ProjectSpec, Sample
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import DEMO_PASSWORD, remember, sign_in

ROWS = ".table__link"


def open_list(
    page: Page,
    base: str,
    *,
    username: str = "anna.claes",
    password: str = DEMO_PASSWORD,
    path: str = "",
    rows: bool = True,
) -> None:
    """Sign in and wait for the Projects list (and, normally, its first row)."""
    remember(page)
    page.goto(f"{base}{path}")
    sign_in(page, username, password)
    if rows:
        expect(page.locator(ROWS).first).to_be_visible()


def api_json(base: str, page: Page, path: str) -> dict:
    """GET an API path with the page's session cookie."""
    cookies = {c.get("name", ""): c.get("value", "") for c in page.context.cookies()}
    response = httpx2.get(f"{base}api/{path}", cookies=cookies)
    assert response.status_code == 200, response.text
    return response.json()


def tree_row(page: Page, name: str) -> Locator:
    """The row (button) of an organisation node in the tree pane."""
    return page.locator(".tree-row").filter(
        has=page.locator(".tree-row__name").get_by_text(re.compile(rf"^{re.escape(name)}$"))
    )


def projects_text(count: int) -> str:
    return f"{count} project" if count == 1 else f"{count} projects"


def shown(projects: list[ProjectSpec]) -> list[ProjectSpec]:
    """What the list shows by default: everything but Stopped (PL-2)."""
    return [p for p in projects if p.status.value != "stopped"]


def test_the_first_fifty_rows_show_and_scrolling_loads_the_next(
    sample_server: str, page: Page, console_errors: list[str], sample: Sample
) -> None:
    open_list(page, sample_server)
    expect(page.locator(ROWS)).to_have_count(50)
    page.locator(".list-more").scroll_into_view_if_needed()
    expect(page.locator(ROWS)).to_have_count(100)
    expected = sorted((p.number for p in shown(sample.projects)), reverse=True)
    numbers = page.locator(".table__number").all_text_contents()
    assert numbers[:100] == [f"#{n}" for n in expected[:100]]  # newest number first, no gaps
    assert console_errors == []


def test_load_more_works_from_the_keyboard(sample_server: str, page: Page) -> None:
    open_list(page, sample_server)
    button = page.get_by_role("button", name="Load more")
    button.focus()
    page.keyboard.press("Enter")
    expect(page.locator(ROWS)).to_have_count(100)


def test_the_header_count_and_the_tree_counts_equal_the_apis(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_list(page, sample_server)
    visible = shown(sample.projects)
    counts = api_json(sample_server, page, "projects/counts")
    assert counts["total"] == len(visible)
    expect(page.locator(".list-count")).to_have_text(projects_text(len(visible)))
    root = page.locator(".tree-row").first
    expect(root.locator(".tree-row__count")).to_have_text(str(len(visible)))
    inside_stl = sum(1 for p in visible if p.node.split("/")[0] == "STL")
    expect(tree_row(page, "STL").locator(".tree-row__count")).to_have_text(str(inside_stl))


def test_stopped_projects_are_hidden_until_their_chip_is_selected(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_list(page, sample_server)
    stopped = sum(1 for p in sample.projects if p.status.value == "stopped")
    chip = page.get_by_role("button", name=re.compile(rf"^Stopped\s*{stopped}$"))
    expect(chip).to_have_attribute("aria-pressed", "false")  # offered with its count, not applied
    assert "Stopped" not in page.locator(".status-pill").all_text_contents()

    chip.click()
    expect(chip).to_have_attribute("aria-pressed", "true")
    expect(page).to_have_url(re.compile(r"status=stopped"))
    expect(page.locator(".list-count")).to_have_text(projects_text(stopped))
    assert {t.strip() for t in page.locator(".status-pill").all_text_contents()} == {"Stopped"}

    chip.click()  # selecting it again clears it
    expect(chip).to_have_attribute("aria-pressed", "false")
    expect(page).not_to_have_url(re.compile(r"status="))


def test_selecting_a_department_filters_rows_and_counts(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_list(page, sample_server)
    tree_row(page, "Hot rolling").click()
    inside = [p for p in shown(sample.projects) if p.node.split("/")[0] == "Hot rolling"]
    expect(page.locator(".list-count")).to_have_text(projects_text(len(inside)))
    expect(page).to_have_url(re.compile(r"node=\d+"))
    expect(page.locator(".crumbs__title")).to_have_text("Hot rolling")
    expect(page.locator(ROWS)).to_have_count(len(inside))
    assert set(page.locator(".table__sub").all_text_contents()) == {
        p.node.split("/")[-1] for p in inside
    }


def test_the_breadcrumb_menu_goes_down_a_level(sample_server: str, page: Page) -> None:
    open_list(page, sample_server)
    page.get_by_role("button", name="Inside Brightwater Industries").click()
    menu = page.get_by_role("menu")
    expect(menu.get_by_role("menuitem", name=re.compile("^STL"))).to_be_visible()
    menu.get_by_role("menuitem", name=re.compile("^Logistics")).click()
    expect(page.locator(".crumbs__title")).to_have_text("Logistics")
    expect(page.locator(".crumbs__ancestor")).to_have_text(["Brightwater Industries"])
    page.locator(".crumbs__ancestor").click()  # up again
    expect(page.locator(".crumbs__title")).to_have_text("Brightwater Industries")


def test_the_header_filters_narrow_the_list(sample_server: str, page: Page, sample: Sample) -> None:
    open_list(page, sample_server)
    named = [p for p in shown(sample.projects) if "sensor" in p.name.casefold()]
    page.get_by_label("Filter by project name").fill("SENSOR")
    expect(page.locator(".list-count")).to_have_text(projects_text(len(named)))
    expect(page).to_have_url(re.compile(r"name=SENSOR"))

    by_rivera = [p for p in named if "rivera" in p.coordinator.casefold()]
    assert by_rivera  # the design's "Sensor retrofit on conveyor 4"
    page.get_by_label("Filter by coordinator").fill("rivera")
    expect(page.locator(".list-count")).to_have_text(projects_text(len(by_rivera)))

    page.get_by_label("Filter by project name").fill("")
    page.get_by_label("Filter by coordinator").fill("")
    expect(page).not_to_have_url(re.compile(r"name=|coordinator="))
    expect(page.locator(".list-count")).to_have_text(projects_text(len(shown(sample.projects))))


def test_the_top_search_narrows_the_list_and_matches_the_api(
    sample_server: str, page: Page
) -> None:
    open_list(page, sample_server)
    page.get_by_label("Search projects").fill("conveyor")
    expect(page).to_have_url(re.compile(r"q=conveyor"))
    total = api_json(sample_server, page, "projects?q=conveyor")["total"]
    assert total >= 1
    expect(page.locator(".list-count")).to_have_text(projects_text(total))
    expect(page.locator(ROWS).filter(has_text="Sensor retrofit on conveyor 4")).to_have_count(1)


def test_the_search_switches_to_projects_from_another_view(sample_server: str, page: Page) -> None:
    open_list(page, sample_server)
    page.get_by_role("link", name="My timesheet").click()
    expect(page).to_have_url(re.compile(r"/timesheet$"))
    page.get_by_label("Search projects").fill("pallet")
    expect(page).to_have_url(re.compile(r"/projects\?q=pallet"))
    expect(page.locator(ROWS).filter(has_text="Recycled pallet programme")).to_have_count(1)


def test_ctrl_k_focuses_the_search(sample_server: str, page: Page) -> None:
    open_list(page, sample_server)
    page.locator("main .eyebrow").click()  # somewhere neutral
    expect(page.get_by_label("Search projects")).not_to_be_focused()
    page.keyboard.press("Control+K")
    expect(page.get_by_label("Search projects")).to_be_focused()


def test_an_empty_result_says_so(sample_server: str, page: Page) -> None:
    open_list(page, sample_server, path="projects?q=zzzz-nothing-like-this", rows=False)
    expect(
        page.get_by_text("No projects match. Try another branch or clear the search.")
    ).to_be_visible()
    expect(page.locator(".list-count")).to_have_text("0 projects")


def test_rows_are_links_that_open_the_project_and_carry_the_filters(
    sample_server: str, page: Page
) -> None:
    open_list(page, sample_server, path="projects?q=4102")
    row = page.locator(ROWS).first
    # a real link (Ctrl/middle click work) that remembers the list it came from (PP-1)
    assert row.get_attribute("href") == "projects/4102?q=4102"
    row.click()
    expect(page).to_have_url(re.compile(r"/projects/4102\?q=4102$"))
    expect(page.get_by_role("heading", name="Sensor retrofit on conveyor 4")).to_be_visible()
    page.go_back()
    expect(page.locator(ROWS).first).to_be_visible()


def test_creating_a_project_opens_it_with_the_next_number(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_list(page, sample_server, username="admin", password=TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="+ New project").click()
    next_number = max(p.number for p in sample.projects) + 1
    dialog = page.get_by_role("dialog", name="New project")
    dialog.get_by_label("Name", exact=True).fill("Brand new from the browser")
    dialog.get_by_label("Coordinator").fill("Anna")
    dialog.get_by_role("option", name=re.compile("Anna Claes")).click()
    dialog.get_by_label("Start", exact=True).fill("2026-11-02")
    dialog.get_by_label("End", exact=True).fill("2027-02-26")
    dialog.get_by_label("Start with the standard phases").check()
    dialog.get_by_role("button", name="Create project").click()
    expect(page).to_have_url(re.compile(rf"/projects/{next_number}$"))
    expect(page.get_by_role("heading", name="Brand new from the browser")).to_be_visible()
    expect(page.get_by_text(f"#{next_number}")).to_be_visible()


def test_a_viewer_sees_no_new_project_button(sample_server: str, page: Page) -> None:
    open_list(page, sample_server)
    expect(page.get_by_role("button", name="+ New project")).to_have_count(0)
