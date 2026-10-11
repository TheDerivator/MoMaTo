"""People planning in a real browser. [PPL-1] [PPL-2] [PPL-3] [PPL-4] [PPL-5] [PPL-6] [PPL-7]"""

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.conftest import remember, sign_in

ROWS = ".pp-person"


def open_people(page: Page, base: str, query: str = "", *, username: str = "anna.claes") -> None:
    remember(page)
    page.goto(f"{base}people{query}")
    sign_in(page, username)
    expect(page.locator(ROWS).first).to_be_visible()


def person(page: Page, name: str) -> Locator:
    return page.locator(ROWS).filter(has=page.locator(".pp-person__name", has_text=name))


def test_planned_is_the_default_with_eight_quarters_and_the_current_one_marked(
    sample_server: str, page: Page
) -> None:
    open_people(page, sample_server)
    expect(page.locator(".crumbs__title")).to_have_text("Brightwater Industries")
    expect(page.locator(".pp-range")).to_have_text("Quarters 2026 – 2027 · days")
    expect(page.locator(".pp-head__bucket")).to_have_text(
        ["Q1/26", "Q2/26", "Q3/26", "Q4/26", "Q1/27", "Q2/27", "Q3/27", "Q4/27"]
    )
    expect(page.locator(".pp-head__bucket--now")).to_have_text("Q4/26")
    expect(page.get_by_role("button", name="Planned")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("group", name="Period")).to_have_count(0)  # only for Spent and Compare
    expect(page.locator(".list-count")).to_have_text("70 people")
    expect(page.locator(ROWS)).to_have_count(70)


def test_a_row_shows_planned_days_against_availability(sample_server: str, page: Page) -> None:
    open_people(page, sample_server)
    anna = person(page, "Anna Claes").locator(".pp-row--person")
    expect(anna.locator(".pp-person__node")).to_have_text("Quality")
    expect(anna.locator(".pp-total__value")).to_have_text("223 d")  # 2026
    expect(anna.locator(".pp-total__sub")).to_have_text("22 d free")  # of her 245 days
    cells = anna.locator(".pp-cell__value")
    expect(cells).to_have_count(8)
    expect(cells.nth(3)).to_have_text("59")  # Q4/26: 23 + 16.5 + 13 + 6.5 planned days
    expect(person(page, "Eva Janssens").locator(".pp-total__sub")).to_contain_text("free")


def test_mode_and_period_are_in_the_url_and_survive_a_reload(
    sample_server: str, page: Page
) -> None:
    open_people(page, sample_server)
    page.get_by_role("button", name="Spent").click()
    expect(page).to_have_url(re.compile(r"/people\?mode=spent$"))
    expect(page.get_by_role("group", name="Period")).to_be_visible()
    expect(page.locator(".pp-range")).to_have_text("Week 40 · 28 Sep – 2 Oct 2026 · hours")
    expect(page.locator(".pp-head__bucket")).to_have_text(
        ["Mon28 Sep", "Tue29 Sep", "Wed30 Sep", "Thu1 Oct", "Fri2 Oct"]
    )

    page.get_by_role("button", name="Past month").click()
    expect(page).to_have_url(re.compile(r"mode=spent&period=month"))
    expect(page.locator(".pp-head__bucket")).to_have_text(
        ["Wk 377 Sep", "Wk 3814 Sep", "Wk 3921 Sep", "Wk 4028 Sep"]
    )

    page.get_by_role("button", name="Compare").click()
    page.get_by_role("button", name="Past year").click()
    expect(page).to_have_url(re.compile(r"mode=compare&period=year"))
    page.reload()
    expect(page.get_by_role("button", name="Compare")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("button", name="Past year")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".pp-range")).to_have_text("October 2025 – September 2026 · days")
    expect(page.locator(".pp-head__bucket")).to_have_count(12)


def test_hours_of_other_departments_are_counted_not_shown(sample_server: str, page: Page) -> None:
    open_people(page, sample_server, "?mode=spent&period=month")
    expect(page.get_by_role("note")).to_have_text(
        "59 people in this branch whose hours you can't see."
    )
    expect(page.locator(ROWS)).to_have_count(11)  # her own department
    page.get_by_role("button", name="Planned").click()
    expect(page.locator(ROWS)).to_have_count(70)  # planned is for everyone
    expect(page.get_by_role("note")).to_have_count(0)


def test_a_branch_outside_the_viewers_department_has_no_spent_rows(
    sample_server: str, page: Page
) -> None:
    open_people(page, sample_server, "?mode=spent&period=month")
    page.get_by_role("button", name="Inside Brightwater Industries").click()
    page.get_by_role("menuitem", name=re.compile("^IT & automation")).click()
    expect(page.locator(".crumbs__title")).to_have_text("IT & automation")
    expect(
        page.get_by_text("You may not see the hours of the people in this branch.")
    ).to_be_visible()
    expect(page.get_by_role("note")).to_have_text(
        "9 people in this branch whose hours you can't see."
    )


def test_expanding_a_person_shows_project_lines_and_a_line_opens_people_and_days(
    sample_server: str, page: Page
) -> None:
    open_people(page, sample_server)
    row = person(page, "Anna Claes")
    row.get_by_role("button", name=re.compile("show projects")).click()
    lines = row.locator(".pp-line")
    expect(lines.first).to_be_visible()
    link = lines.get_by_role("link", name=re.compile("Sensor retrofit")).first
    expect(link).to_have_attribute("href", re.compile(r"projects/4102/people"))
    link.click()
    expect(page).to_have_url(re.compile(r"/projects/4102/people"))
    expect(page.locator(".people-days")).to_be_visible()


def test_spent_lines_end_with_other_work_and_compare_lines_show_spent_over_planned(
    sample_server: str, page: Page
) -> None:
    open_people(page, sample_server, "?mode=compare&period=month")
    row = person(page, "Anna Claes")
    row.get_by_role("button", name=re.compile("show projects")).click()
    expect(row.locator(".pp-line").last).to_contain_text("Other work")
    expect(row.locator(".pp-total__sub")).to_contain_text("% of plan")
    project = row.locator(".pp-line").filter(has_text="Vision-based quality check")
    expect(project.locator(".pp-line__total")).to_contain_text("/")  # spent / planned

    page.get_by_role("button", name="Spent").click()  # the row stays open; its lines are reloaded
    row = person(page, "Anna Claes")
    expect(row.locator(".pp-line").filter(has_text="Other work")).to_have_count(1)
    expect(row.locator(".pp-line__total").first).not_to_contain_text("/")  # no plan in Spent


def test_the_person_filter_and_the_branch_narrow_the_rows(sample_server: str, page: Page) -> None:
    open_people(page, sample_server)
    page.get_by_label("Filter by person").fill("claes")
    expect(page.locator(ROWS)).to_have_count(1)
    expect(page.locator(".pp-person__name")).to_have_text("Anna Claes")
    page.get_by_label("Filter by person").fill("")
    expect(page.locator(ROWS)).to_have_count(70)

    page.locator(".tree-row").filter(
        has=page.locator(".tree-row__name", has_text=re.compile("^STL$"))
    ).click()
    expect(page).to_have_url(re.compile(r"node=\d+"))
    expect(page.locator(ROWS)).to_have_count(11)
    expect(page.locator(".crumbs__title")).to_have_text("STL")
    # the tree's counts are the people of each branch (SH-3)
    expect(
        page.locator(".tree-row")
        .filter(has=page.locator(".tree-row__name", has_text=re.compile("^STL$")))
        .locator(".tree-row__count")
    ).to_have_text("11")


def test_a_person_can_be_deep_linked_open(sample_server: str, page: Page) -> None:
    remember(page)
    page.goto(f"{sample_server}people")
    sign_in(page, "anna.claes")
    expect(page.locator(ROWS).first).to_be_visible()
    page.get_by_role("button", name=re.compile("Anna Claes: show projects")).click()
    expect(page.locator(".pp-line").first).to_be_visible()
    page.get_by_role("button", name=re.compile("Anna Claes: hide projects")).click()
    expect(page.locator(".pp-line")).to_have_count(0)
