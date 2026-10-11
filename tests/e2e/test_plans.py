"""Action plans in a real browser: branches, the timeline, selection, the feed, managing plans and
linking projects. [AP-1] [AP-2] [AP-3] [AP-4] [AP-5] [AP-6] [AP-7] [AP-8]"""

import re

import httpx2
from playwright.sync_api import Locator, Page, expect
from sqlalchemy import delete

from momato.db.models import DefaultGrant
from momato.db.session import Database
from momato.services.sample_data import Sample
from tests.conftest import DEMO_PASSWORD, TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in

DIGITAL = "Digital plant"  # owned by IT & automation, the first plan of the sample
SENSORS = 4102  # in the Digital plant, under IT & automation
SENSORS_NAME = "Sensor retrofit on conveyor 4"


def open_plans(
    page: Page,
    base: str,
    query: str = "",
    *,
    username: str = "anna.claes",
    password: str = DEMO_PASSWORD,
    timeline: bool = True,
) -> None:
    remember(page)
    page.goto(f"{base}plans{query}")
    sign_in(page, username, password)
    expect(page.locator(".plans-page")).to_be_visible()
    if timeline:
        expect(page.locator(".plan-timeline__row--head")).to_be_visible()


def api_json(base: str, page: Page, path: str) -> dict | list:
    cookies = {c.get("name", ""): c.get("value", "") for c in page.context.cookies()}
    response = httpx2.get(f"{base}api/{path}", cookies=cookies)
    assert response.status_code == 200, response.text
    return response.json()


def tree_row(page: Page, name: str) -> Locator:
    return page.locator(".tree-row").filter(
        has=page.locator(".tree-row__name").get_by_text(re.compile(rf"^{re.escape(name)}$"))
    )


def group(page: Page, name: str) -> Locator:
    return page.locator(".plan-group").filter(
        has=page.locator(".plan-group__name", has_text=re.compile(rf"^{re.escape(name)}$"))
    )


def project_row(page: Page, name: str) -> Locator:
    return page.locator(".plan-project").filter(
        has=page.locator(".plan-project__name", has_text=re.compile(rf"^{re.escape(name)}$"))
    )


def plan_names(page: Page) -> Locator:
    return page.locator(".plan-tab__name")


# ---------------------------------------------------------------- branches


def test_the_root_shows_every_plan_and_the_first_is_chosen(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_plans(page, sample_server)
    expect(page.locator(".plans-page .eyebrow")).to_have_text("Action plans")
    expect(page.locator(".list-count")).to_have_text(f"{len(sample.plans)} plans")
    expect(plan_names(page)).to_have_text([p.name for p in sample.plans])
    first = page.locator(".plan-tab").first
    expect(first).to_have_attribute("aria-pressed", "true")
    expect(first.locator(".plan-tab__count")).to_have_text(str(len(sample.plans[0].projects)))
    expect(page.locator(".plan-name")).to_have_text(DIGITAL)
    expect(page.locator(".plan-meta")).to_have_text(
        "Owned by IT & automation · coordinated by Tomás Rivera"
        " · includes projects from 4 departments"
    )


def test_selecting_a_department_shows_only_the_plans_it_owns(
    sample_server: str, page: Page
) -> None:
    open_plans(page, sample_server)
    expect(tree_row(page, "Coating lines").locator(".tree-row__count")).to_have_text("2")

    tree_row(page, "Coating lines").click()
    expect(page).to_have_url(re.compile(r"/plans\?node=\d+$"))
    expect(page.locator(".list-count")).to_have_text("2 plans")
    expect(plan_names(page)).to_have_text(["Line performance 2026", "Zero defects in coating"])
    expect(page.locator(".plan-meta")).to_contain_text("Owned by Coating lines")

    tree_row(page, "IT & automation").click()
    expect(page.locator(".list-count")).to_have_text("1 plan")
    expect(plan_names(page)).to_have_text([DIGITAL])

    tree_row(page, "Brightwater Industries").click()
    expect(page.locator(".list-count")).to_have_text("12 plans")


def test_a_branch_without_plans_says_so(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server)
    tree_row(page, "Quality").click()
    expect(page.locator(".plan-empty__title")).to_have_text("No action plans owned by Quality")
    expect(page.locator(".list-count")).to_have_text("0 plans")
    expect(page.locator(".plan-tab")).to_have_count(0)
    expect(page.get_by_role("button", name="+ New plan")).to_have_count(0)  # no plan.manage
    # the plans of a whole department are still found one level up
    tree_row(page, "STL").click()
    expect(plan_names(page)).to_have_text(["Skills and training 2027"])


def test_a_plan_tab_is_in_the_url_and_survives_a_reload(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server)
    page.locator(".plan-tab").filter(has_text="Safe workplace").click()
    expect(page).to_have_url(re.compile(r"/plans/\d+$"))
    expect(page.locator(".plan-name")).to_have_text("Safe workplace")
    page.reload()
    expect(page.locator(".plan-name")).to_have_text("Safe workplace")
    expect(page.locator(".plan-tab").filter(has_text="Safe workplace")).to_have_attribute(
        "aria-pressed", "true"
    )


# ---------------------------------------------------------------- totals and the timeline


def test_totals_and_rows_follow_the_overview_of_the_api(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server)
    plans = api_json(sample_server, page, "plans")
    digital = next(p for p in plans if p["name"] == DIGITAL)  # pyright: ignore[reportCallIssue]
    overview = api_json(sample_server, page, f"plans/{digital['id']}/overview")
    assert isinstance(overview, dict)
    totals = page.locator(".plan-totals")
    expect(totals.locator(".plan-totals__number")).to_have_text(f"{overview['days']['logged']:.1f}")
    expect(totals).to_contain_text(f"of {overview['days']['planned']:.1f} planned days logged")
    expect(totals).to_contain_text(f"across {overview['project_count']} projects")
    expect(totals).to_contain_text("Tick = expected by today")

    groups = page.locator(".plan-group")
    expect(groups).to_have_count(len(overview["groups"]))
    expect(page.locator(".plan-group__name")).to_have_text([g["name"] for g in overview["groups"]])
    expect(page.locator(".plan-group__owner")).to_have_count(1)  # the owner's group, first
    expect(groups.first.locator(".plan-group__owner")).to_have_text("Owner")
    expect(groups.first.locator(".plan-group__name")).to_have_text("IT & automation")
    expect(page.locator(".plan-project")).to_have_count(overview["project_count"])


def test_a_group_collapses_and_opens_again(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server)
    it = group(page, "IT & automation")
    toggle = it.get_by_role("button", name=re.compile("^IT & automation"))
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(project_row(page, SENSORS_NAME)).to_be_visible()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(project_row(page, SENSORS_NAME)).to_have_count(0)
    expect(group(page, "Central maintenance").locator(".plan-project").first).to_be_visible()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(project_row(page, SENSORS_NAME)).to_be_visible()


# ---------------------------------------------------------------- selection, summary and feed


def test_selecting_a_project_shows_its_summary_and_the_latest_on_it(
    sample_server: str, page: Page
) -> None:
    open_plans(page, sample_server)
    expect(page.locator(".plan-feed .card__title")).to_have_text("Recent across this plan")
    expect(page.locator(".plan-summary")).to_have_count(0)

    row = project_row(page, SENSORS_NAME)
    row.get_by_role("button").click()
    expect(page).to_have_url(re.compile(rf"/plans/\d+\?project={SENSORS}$"))
    expect(row).to_have_class(re.compile("plan-project--on"))
    summary = page.locator(".plan-summary")
    expect(summary).to_be_visible()
    expect(summary.locator(".plan-summary__name")).to_have_text(SENSORS_NAME)
    expect(summary).to_contain_text(f"#{SENSORS}")
    expect(summary).to_contain_text("Tomás Rivera")
    expect(summary.get_by_role("link", name=re.compile("^Open project"))).to_have_attribute(
        "href", f"projects/{SENSORS}"
    )
    expect(page.locator(".plan-feed .card__title")).to_have_text("Latest on this project")
    for item in page.locator(".plan-feed__item").all():
        expect(item.locator(".plan-feed__project")).to_contain_text(f"#{SENSORS} ")

    # clicking the row again, and the × of the summary, both clear the selection
    row.get_by_role("button").click()
    expect(page.locator(".plan-summary")).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/plans/\d+$"))
    row.get_by_role("button").click()
    summary.get_by_role("button", name="Back to the whole plan").click()
    expect(page.locator(".plan-summary")).to_have_count(0)
    expect(page.locator(".plan-feed .card__title")).to_have_text("Recent across this plan")


def test_the_selection_survives_a_reload(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server)
    project_row(page, SENSORS_NAME).get_by_role("button").click()
    expect(page.locator(".plan-summary")).to_be_visible()
    page.reload()
    expect(page.locator(".plan-summary__name")).to_have_text(SENSORS_NAME)
    expect(page.locator(".plan-project--on")).to_have_count(1)


def test_the_feed_has_at_most_eight_items_and_opens_the_remarks_or_the_logbook(
    sample_server: str, page: Page
) -> None:
    open_plans(page, sample_server)
    items = page.locator(".plan-feed__item")
    expect(items.first).to_be_visible()
    assert 0 < items.count() <= 8

    remark = items.filter(has=page.locator(".plan-feed__excerpt")).first
    change = items.filter(has=page.locator(".plan-feed__change")).first
    expect(remark).to_be_visible()
    expect(change).to_be_visible()
    remark_href = remark.get_attribute("href")
    change_href = change.get_attribute("href")
    assert remark_href is not None
    assert re.fullmatch(r"projects/\d+/remarks", remark_href), remark_href
    assert change_href is not None
    assert re.fullmatch(r"projects/\d+/logbook", change_href), change_href

    change.click()
    expect(page).to_have_url(re.compile(re.escape(change_href) + "$"))
    expect(page.locator(".log-entry").first).to_be_visible()

    page.go_back()
    expect(page.locator(".plan-timeline__row--head")).to_be_visible()
    page.locator(".plan-feed__item").filter(has=page.locator(".plan-feed__excerpt")).first.click()
    expect(page).to_have_url(re.compile(re.escape(remark_href) + "$"))
    expect(page.locator(".remark").first).to_be_visible()


# ---------------------------------------------------------------- managing plans


def test_without_plan_manage_there_is_no_way_to_create_edit_or_delete(
    sample_server: str, page: Page
) -> None:
    open_plans(page, sample_server)
    expect(page.get_by_role("button", name="+ New plan")).to_have_count(0)
    expect(page.get_by_role("button", name="Plan actions")).to_have_count(0)
    # a viewer cannot link projects either: the search button is for people who can edit
    expect(page.get_by_role("button", name="+ Add project")).to_have_count(0)


def test_a_new_plan_takes_a_project_from_another_department_and_logs_it(
    sample_server: str, page: Page
) -> None:
    open_plans(page, sample_server, username="admin", password=TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="+ New plan").click()
    dialog = page.get_by_role("dialog", name="New plan")
    dialog.get_by_label("Name").fill("Quality push")
    dialog.get_by_label("Description").fill("Fewer claims, faster answers.")
    dialog.get_by_label("Owned by").select_option(label="– STL")
    dialog.get_by_label("Coordinator").fill("Anna")
    dialog.get_by_role("option", name=re.compile("^Anna Claes")).click()
    dialog.get_by_role("radio", name="Hue 155").click()
    dialog.get_by_role("button", name="Create plan").click()
    expect(dialog).to_have_count(0)

    # the new plan is chosen, owned by STL, empty
    expect(page.locator(".plan-name")).to_have_text("Quality push")
    expect(page).to_have_url(re.compile(r"/plans/\d+$"))
    expect(page.locator(".plan-meta")).to_contain_text("Owned by STL")
    expect(page.locator(".plan-meta")).to_contain_text("coordinated by Anna Claes")
    expect(page.locator(".plan-description")).to_have_text("Fewer claims, faster answers.")
    expect(page.locator(".plan-timeline")).to_contain_text("No projects attached to this plan yet")
    expect(page.locator(".plan-tab").filter(has_text="Quality push")).to_be_visible()
    expect(page.locator(".list-count")).to_have_text("13 plans")

    # a project of IT & automation (not STL) joins it and appears under its own department
    page.get_by_role("button", name="+ Add project").click()
    finder = page.get_by_role("dialog", name="Add a project to this plan")
    finder.get_by_role("combobox").fill(str(SENSORS))
    finder.get_by_role("option", name=re.compile(f"^#{SENSORS} ")).click()
    expect(group(page, "IT & automation")).to_be_visible()
    expect(group(page, "IT & automation").locator(".plan-group__owner")).to_have_count(0)
    expect(project_row(page, SENSORS_NAME)).to_be_visible()
    expect(page.locator(".plan-totals")).to_contain_text("across 1 project")
    expect(page.locator(".plan-summary__name")).to_have_text(SENSORS_NAME)  # selected on adding

    # and the project's logbook says so, and its plan pills show the plan
    page.get_by_role("link", name=re.compile("^Open project")).click()
    expect(page.locator(".project-title")).to_have_text(SENSORS_NAME)
    expect(page.get_by_role("link", name="Quality push")).to_be_visible()
    page.get_by_role("navigation", name="Project sections").get_by_role(
        "link", name=re.compile("^Logbook")
    ).click()
    first = page.locator(".log-entry").first
    expect(first).to_contain_text("Added to Quality push")

    # removing it again from the plan page empties the plan
    page.go_back()
    page.go_back()
    expect(page.locator(".plan-summary")).to_be_visible()
    page.get_by_role("button", name="Remove from plan").click()
    expect(page.locator(".plan-timeline")).to_contain_text("No projects attached to this plan yet")
    expect(page.locator(".plan-summary")).to_have_count(0)


def test_a_plan_is_edited_and_deleted_from_its_menu(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server, username="admin", password=TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="Plan actions").click()
    page.get_by_role("menuitem", name="Edit plan").click()
    dialog = page.get_by_role("dialog", name="Edit plan")
    expect(dialog.get_by_label("Name")).to_have_value(DIGITAL)
    dialog.get_by_label("Name").fill("Digital plant 2")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_have_count(0)
    expect(page.locator(".plan-name")).to_have_text("Digital plant 2")
    expect(plan_names(page).first).to_have_text("Digital plant 2")

    page.get_by_role("button", name="Plan actions").click()
    page.get_by_role("menuitem", name="Delete plan").click()
    confirm = page.get_by_role("dialog", name=re.compile("^Delete"))
    confirm.get_by_role("button", name="Delete plan").click()
    expect(confirm).to_have_count(0)
    expect(page.locator(".list-count")).to_have_text("11 plans")
    expect(plan_names(page).filter(has_text="Digital plant")).to_have_count(0)
    # the project it held lost the pill
    page.goto(f"{sample_server}projects/{SENSORS}")
    expect(page.locator(".project-title")).to_have_text(SENSORS_NAME)
    expect(page.get_by_role("link", name="Digital plant 2")).to_have_count(0)


def test_a_cancelled_dialog_changes_nothing(sample_server: str, page: Page) -> None:
    open_plans(page, sample_server, username="admin", password=TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="+ New plan").click()
    dialog = page.get_by_role("dialog", name="New plan")
    dialog.get_by_label("Name").fill("Never created")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(page.locator(".list-count")).to_have_text("12 plans")


# ---------------------------------------------------------------- what a viewer cannot see


def test_projects_the_viewer_cannot_see_are_absent_from_rows_totals_and_feed(
    sample_database: Database, sample_server: str, page: Page, sample: Sample
) -> None:
    """[AP-8]"""
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))  # nobody is a Viewer by default any more
    open_plans(page, sample_server, username="tomas.rivera")
    mine = {
        p.number
        for p in sample.projects
        if "Tomás Rivera" in p.members and p.number in sample.plans[0].projects
    }
    assert SENSORS in mine
    expect(page.locator(".plan-tab").first.locator(".plan-tab__count")).to_have_text(str(len(mine)))
    expect(page.locator(".plan-project")).to_have_count(len(mine))
    expect(page.locator(".plan-totals")).to_contain_text(f"across {len(mine)} project")
    shown = page.locator(".plan-feed__project").all_text_contents()
    numbers = {int(re.match(r"#(\d+) ", text).group(1)) for text in shown}  # pyright: ignore
    assert numbers <= mine
