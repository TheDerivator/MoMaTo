"""The project page in a real browser: frame, status and plans, titles, the Overview, the logbook
and All details; optimistic edits and stale versions. [PP-1] [PP-2] [PP-3] [PP-4] [PP-5] [PP-6]
[PP-7] [OV-1] [OV-3] [OV-4] [OV-5] [LB-2] [LB-3] [LB-4] [DT-1] [DT-3]"""

import re

from playwright.sync_api import Browser, Locator, Page, expect

from momato.services.sample_data import Sample
from tests.e2e.conftest import remember, sign_in

SENSORS = 4102  # Tomás Rivera coordinates it; Anna, Sofia and Pieter are members
PROGRESS = "In progress"


def open_project(
    page: Page,
    base: str,
    number: int = SENSORS,
    tab: str = "",
    *,
    username: str = "tomas.rivera",
    query: str = "",
) -> None:
    remember(page)
    path = f"projects/{number}" + (f"/{tab}" if tab else "")
    page.goto(f"{base}{path}{query}")
    sign_in(page, username)
    expect(page.locator(".project-title")).to_be_visible()


def title_button(page: Page) -> Locator:
    return page.get_by_role("heading", level=1).get_by_role("button")


def status_pill(page: Page) -> Locator:
    return page.locator(".badges .status-pill")


def tab_link(page: Page, name: str) -> Locator:
    return page.get_by_role("navigation", name="Project sections").get_by_role(
        "link", name=re.compile(rf"^{name}")
    )


def pick_status(page: Page, label: str) -> None:
    status_pill(page).click()
    page.get_by_role("menuitemradio", name=label).click()


# ---------------------------------------------------------------- the frame


def test_the_frame_shows_the_important_metadata(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    expect(page.locator(".number-pill")).to_have_text("#4102")
    expect(status_pill(page)).to_contain_text(PROGRESS)
    expect(page.get_by_role("link", name="Digital plant")).to_be_visible()
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    expect(page.locator(".org-trail__node")).to_have_text(
        ["Brightwater Industries", "IT & automation", "Level 1-2 automation"]
    )
    expect(tab_link(page, "Remarks")).to_contain_text("4")
    expect(tab_link(page, "Logbook")).to_contain_text("7")
    expect(tab_link(page, "Overview")).to_have_attribute("aria-current", "page")
    expect(page).to_have_title("#4102 Sensor retrofit on conveyor 4 · MoMaTo")


def test_the_tab_is_part_of_the_url(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    tab_link(page, "Logbook").click()
    expect(page).to_have_url(re.compile(r"/projects/4102/logbook$"))
    page.reload()
    expect(tab_link(page, "Logbook")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("group", name="Filter the logbook")).to_be_visible()
    tab_link(page, "All details").click()
    expect(page).to_have_url(re.compile(r"/projects/4102/details$"))


def test_arrows_step_through_the_list_it_came_from_and_keep_the_tab(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_project(page, sample_server, tab="logbook", query="?status=progress")
    numbers = sorted(
        (p.number for p in sample.projects if p.status.value == "progress"), reverse=True
    )
    position = numbers.index(SENSORS)
    expect(page.locator(".stepper__position")).to_have_text(f"{position + 1} of {len(numbers)}")

    page.get_by_role("button", name="Next project").click()
    expect(page).to_have_url(
        re.compile(rf"/projects/{numbers[position + 1]}/logbook\?status=progress$")
    )
    expect(page.locator(".number-pill")).to_have_text(f"#{numbers[position + 1]}")
    expect(page.locator(".stepper__position")).to_have_text(f"{position + 2} of {len(numbers)}")
    page.get_by_role("button", name="Previous project").click()
    expect(page.locator(".number-pill")).to_have_text("#4102")

    page.get_by_role("link", name="← Projects").click()  # back to the list as it was
    expect(page).to_have_url(re.compile(r"/projects\?status=progress$"))
    expect(page.locator(".table__link").first).to_be_visible()


def test_the_ends_of_the_list_have_one_disabled_arrow(
    sample_server: str, page: Page, sample: Sample
) -> None:
    newest = max(p.number for p in sample.projects if p.status.value != "stopped")
    open_project(page, sample_server, newest)
    expect(page.get_by_role("button", name="Previous project")).to_be_disabled()
    expect(page.get_by_role("button", name="Next project")).to_be_enabled()
    expect(page.locator(".stepper__position")).to_contain_text("1 of")


def test_an_unknown_or_invisible_project_says_so(sample_server: str, page: Page) -> None:
    open_project_missing = f"{sample_server}projects/999999"
    remember(page)
    page.goto(open_project_missing)
    sign_in(page, "anna.claes")
    expect(page.get_by_role("heading", name="Not found or no access")).to_be_visible()


# ---------------------------------------------------------------- status and plans


def test_changing_the_status_updates_the_pill_and_the_logbook(
    sample_server: str, page: Page
) -> None:
    open_project(page, sample_server)
    pick_status(page, "On hold")
    expect(status_pill(page)).to_contain_text("On hold")  # at once
    expect(tab_link(page, "Logbook")).to_contain_text("8")

    tab_link(page, "Logbook").click()
    first = page.locator(".log-entry").first
    expect(first).to_contain_text("You changed status")
    expect(first.locator(".log-chip--old")).to_have_text(PROGRESS)
    expect(first.locator(".log-chip--new")).to_have_text("On hold")
    page.reload()
    expect(page.locator(".log-entry")).to_have_count(8)


def test_choosing_the_current_status_changes_nothing(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    pick_status(page, PROGRESS)
    expect(tab_link(page, "Logbook")).to_contain_text("7")


def test_action_plans_are_toggled_from_a_checklist(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    page.get_by_role("button", name="+ Action plan").click()
    safe = page.get_by_role("menuitemcheckbox", name="Safe workplace")
    expect(safe).to_have_attribute("aria-checked", "false")
    expect(page.get_by_role("menuitemcheckbox", name="Digital plant")).to_have_attribute(
        "aria-checked", "true"
    )
    safe.click()
    expect(page.get_by_role("link", name="Safe workplace")).to_be_visible()
    expect(tab_link(page, "Logbook")).to_contain_text("8")

    page.get_by_role("menuitemcheckbox", name="Safe workplace").click()  # the menu stays open
    expect(page.get_by_role("link", name="Safe workplace")).to_have_count(0)
    page.keyboard.press("Escape")
    expect(page.get_by_role("menu", name="Action plans")).to_have_count(0)
    tab_link(page, "Logbook").click()
    entries = page.locator(".log-entry")
    expect(entries.nth(0)).to_contain_text("Removed from Safe workplace")
    expect(entries.nth(1)).to_contain_text("Added to Safe workplace")


# ---------------------------------------------------------------- the title


def test_renaming_commits_on_enter_and_on_blur_and_cancels_on_escape(
    sample_server: str, page: Page
) -> None:
    open_project(page, sample_server)
    title = page.locator(".project-title")

    title_button(page).click()
    field = page.get_by_label("Project title", exact=True)
    field.fill("Sensor retrofit, line 4")
    field.press("Enter")
    expect(title).to_have_text("Sensor retrofit, line 4")

    title_button(page).click()
    page.get_by_label("Project title", exact=True).fill("Cancelled name")
    page.keyboard.press("Escape")
    expect(title).to_have_text("Sensor retrofit, line 4")

    title_button(page).click()
    page.get_by_label("Project title", exact=True).fill("Blurred name")
    page.locator(".number-pill").click()  # leave the field
    expect(title).to_have_text("Blurred name")

    page.reload()
    expect(page.locator(".project-title")).to_have_text("Blurred name")
    expect(tab_link(page, "Logbook")).to_contain_text("9")  # two renames


def test_an_empty_or_unchanged_title_changes_nothing(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    title_button(page).click()
    page.get_by_label("Project title", exact=True).fill("   ")
    page.keyboard.press("Enter")
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    title_button(page).click()
    expect(page.get_by_label("Project title", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    expect(tab_link(page, "Logbook")).to_contain_text("7")


# ---------------------------------------------------------------- read-only


def test_a_viewer_has_no_editing_affordances(sample_server: str, page: Page) -> None:
    open_project(page, sample_server, username="bram.peeters")
    expect(page.locator(".project-title")).to_have_text("Sensor retrofit on conveyor 4")
    expect(page.locator(".inline-edit")).to_have_count(0)
    expect(page.get_by_role("button", name="+ Action plan")).to_have_count(0)
    expect(page.locator(".badges button.status-pill")).to_have_count(0)
    expect(page.get_by_role("button", name="Change")).to_have_count(0)
    expect(page.get_by_role("button", name="+ Add person")).to_have_count(0)
    tab_link(page, "All details").click()
    expect(page.locator(".inline-edit")).to_have_count(0)
    expect(page.locator(".details__row").first).to_be_visible()


# ---------------------------------------------------------------- overview


def test_the_overview_shows_where_we_are_and_the_days(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_project(page, sample_server)
    spec = next(p for p in sample.projects if p.number == SENSORS)
    phases = page.locator(".phase")
    expect(phases).to_have_count(len(spec.tasks))
    expect(phases.first.locator(".phase__name")).to_have_text(spec.tasks[0].name)
    expect(page.locator(".where__timeline")).to_contain_text("of the timeline behind us")
    expect(page.locator(".days__number")).to_be_visible()
    expect(page.locator(".card__link", has_text="Per person →")).to_be_visible()
    page.get_by_role("link", name="All details →").click()
    expect(page).to_have_url(re.compile(r"/projects/4102/details$"))


def test_the_latest_remark_opens_the_remarks(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    latest = page.locator(".latest")
    expect(latest).to_contain_text("Sofia Lind")
    expect(latest).to_contain_text("First full week of live data")
    latest.locator(".md").click()
    expect(page).to_have_url(re.compile(r"/projects/4102/remarks$"))


def test_editors_change_the_goal_priority_and_dates_in_place(
    sample_server: str, page: Page
) -> None:
    open_project(page, sample_server)
    page.get_by_role("button", name=re.compile(r"^Goal:")).click()
    goal = page.get_by_label("Goal", exact=True)
    goal.fill("Live data from every conveyor.\nAlerts at night.")
    goal.press("Control+Enter")
    expect(page.locator(".goal")).to_contain_text("Alerts at night.")

    page.get_by_role("button", name=re.compile(r"^Priority:")).click()
    page.get_by_label("Priority", exact=True).select_option("low")
    expect(page.locator(".facts__item", has_text="Priority")).to_contain_text("Low")

    page.get_by_role("button", name=re.compile(r"^End date:")).click()
    page.get_by_label("End date", exact=True).fill("2027-04-30")
    page.keyboard.press("Enter")
    expect(page.locator(".facts__item", has_text="End")).to_contain_text("30 Apr 2027")

    page.reload()
    expect(page.locator(".goal")).to_contain_text("Alerts at night.")
    expect(page.locator(".facts__item", has_text="End")).to_contain_text("30 Apr 2027")
    expect(tab_link(page, "Logbook")).to_contain_text("10")  # goal, priority and end date


def test_people_are_added_and_removed_with_a_warning(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    chips = page.locator(".person-chip")
    expect(chips).to_have_count(4)

    page.get_by_role("button", name="+ Add person").click()
    page.get_by_role("combobox", name="Add a person").fill("bram")
    page.get_by_role("option", name=re.compile("Bram Peeters")).click()
    expect(chips).to_have_count(5)
    expect(page.locator(".person-chip", has_text="Bram Peeters")).to_be_visible()

    page.get_by_role("button", name="Remove Bram Peeters").click()
    dialog = page.get_by_role("dialog", name="Remove Bram Peeters?")
    expect(dialog).to_contain_text("planned days on it are removed")
    dialog.get_by_role("button", name="Cancel").click()
    expect(chips).to_have_count(5)

    page.get_by_role("button", name="Remove Bram Peeters").click()
    page.get_by_role("dialog", name="Remove Bram Peeters?").get_by_role(
        "button", name="Remove"
    ).click()
    expect(chips).to_have_count(4)
    # the coordinator has no remove button
    expect(page.get_by_role("button", name="Remove Tomás Rivera")).to_have_count(0)


def test_the_coordinator_is_changed_with_a_person_search(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    page.get_by_role("button", name="Change").click()
    page.get_by_role("combobox", name="New coordinator").fill("sofia")
    page.get_by_role("option", name=re.compile("Sofia Lind")).click()
    expect(page.locator(".person-row__name")).to_have_text("Sofia Lind")
    tab_link(page, "Logbook").click()
    expect(page.locator(".log-entry").first).to_contain_text("You changed coordinator")


# ---------------------------------------------------------------- logbook


def test_the_logbook_filters_by_group(sample_server: str, page: Page, sample: Sample) -> None:
    open_project(page, sample_server, tab="logbook")
    spec = next(p for p in sample.projects if p.number == SENSORS)
    groups = {
        "Title": {"title"},
        "Status": {"status"},
        "Dates": {"start_date", "end_date"},
        "People": {"people", "coordinator"},
        "Action plans": {"action_plans"},
    }
    entries = page.locator(".log-entry")
    expect(entries).to_have_count(len(spec.log))
    for label, fields in groups.items():
        page.get_by_role("button", name=label, exact=True).click()
        expected = sum(1 for e in spec.log if e.field.value in fields)
        if expected:
            expect(entries).to_have_count(expected)
        else:
            expect(page.get_by_text("No changes recorded for this filter.")).to_be_visible()
    page.get_by_role("button", name="Everything").click()
    expect(entries).to_have_count(len(spec.log))
    expect(tab_link(page, "Logbook")).to_contain_text(
        str(len(spec.log))
    )  # the tab keeps the full count


def test_the_logbook_reads_you_and_names_and_is_read_only(sample_server: str, page: Page) -> None:
    open_project(page, sample_server, tab="logbook", username="bram.peeters")
    expect(page.locator(".log-entry").first).to_contain_text("Tomás Rivera changed end date")
    expect(page.locator(".log-entry").last).to_contain_text("Lukas Brandt created the project")
    expect(page.locator(".log-list button, .log-list input")).to_have_count(0)


def test_long_values_are_cut_and_expand(sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    long_goal = "Make every conveyor observable. " * 6
    page.get_by_role("button", name=re.compile(r"^Goal:")).click()
    page.get_by_label("Goal", exact=True).fill(long_goal)
    page.keyboard.press("Control+Enter")
    tab_link(page, "Logbook").click()
    chip = page.locator(".log-entry").first.locator(".log-chip--new")
    expect(chip).to_contain_text("…")
    chip.get_by_role("button", name="more").click()
    expect(chip).to_contain_text(long_goal.strip())
    chip.get_by_role("button", name="less").click()
    expect(chip).to_contain_text("…")


# ---------------------------------------------------------------- all details


def test_details_show_the_profile_cards(sample_server: str, page: Page) -> None:
    open_project(page, sample_server, tab="details")
    cards = page.locator(".details .card__title")
    expect(cards).to_have_text(["Identification", "Organisation", "Classification", "Involvement"])
    row = page.locator(".details__row", has_text="ERP order")
    expect(row).to_contain_text("EO-9554-4102")
    expect(page.locator(".details__row", has_text="Project number")).to_contain_text("#4102")
    expect(page.locator(".details__row", has_text="Department")).to_contain_text(
        "Level 1-2 automation"
    )
    expect(page.locator(".details__row", has_text="Engineering")).to_contain_text("No")


def test_every_field_type_is_edited_in_place_and_survives_a_reload(
    sample_server: str, page: Page
) -> None:
    open_project(page, sample_server, tab="details")
    row = lambda label: page.locator(".details__row", has=page.get_by_text(label, exact=True))  # noqa: E731

    # text
    row("ERP order").get_by_role("button").click()
    page.get_by_label("ERP order", exact=True).fill("EO-0001")
    page.keyboard.press("Enter")
    expect(row("ERP order")).to_contain_text("EO-0001")

    # choice
    row("Activity type").get_by_role("button").click()
    page.get_by_label("Activity type", exact=True).select_option("Study")
    expect(row("Activity type")).to_contain_text("Study")

    # yes / no
    row("Engineering").get_by_role("button").click()
    page.get_by_label("Engineering", exact=True).select_option("yes")
    expect(row("Engineering")).to_contain_text("Yes")

    # tags
    row("Tags").get_by_role("button").click()
    page.get_by_label("Tags", exact=True).fill("quality, belts ,Quality")
    page.keyboard.press("Enter")
    expect(row("Tags")).to_contain_text("quality, belts")

    # person
    row("Budget owner").get_by_role("button").click()  # a choice, to cover clearing
    page.get_by_label("Budget owner", exact=True).select_option("Operations")
    row("Sponsor").get_by_role("button").click()
    page.get_by_role("combobox", name="Choose sponsor").fill("pieter")
    page.get_by_role("option", name=re.compile("Pieter Kools")).click()
    expect(row("Sponsor")).to_contain_text("Pieter Kools")

    # project
    row("Original project").get_by_role("button").click()
    page.get_by_role("textbox", name="Find original project").fill("4307")
    page.get_by_role("option", name=re.compile("#4307")).click()
    expect(row("Original project")).to_contain_text("#4307")

    page.reload()
    expect(row("ERP order")).to_contain_text("EO-0001")
    expect(row("Activity type")).to_contain_text("Study")
    expect(row("Engineering")).to_contain_text("Yes")
    expect(row("Tags")).to_contain_text("quality, belts")
    expect(row("Budget owner")).to_contain_text("Operations")
    expect(row("Sponsor")).to_contain_text("Pieter Kools")
    expect(row("Original project")).to_contain_text("#4307 Digital shift handover")
    # detail fields are not logged (D-016)
    expect(tab_link(page, "Logbook")).to_contain_text("7")


def test_a_value_can_be_cleared(sample_server: str, page: Page) -> None:
    open_project(page, sample_server, tab="details")
    row = page.locator(".details__row", has_text="ERP order")
    row.get_by_role("button").click()
    page.get_by_label("ERP order", exact=True).fill("")
    page.keyboard.press("Enter")
    expect(row).to_contain_text("–")
    page.reload()
    expect(page.locator(".details__row", has_text="ERP order")).to_contain_text("–")


# ---------------------------------------------------------------- two editors


def test_a_stale_edit_says_so_and_reloads(browser: Browser, sample_server: str, page: Page) -> None:
    open_project(page, sample_server)
    other_context = browser.new_context()
    try:
        other = other_context.new_page()
        remember(other)
        other.goto(f"{sample_server}projects/{SENSORS}")
        sign_in(other, "tomas.rivera")
        expect(other.locator(".project-title")).to_be_visible()
        title_button(other).click()
        other.get_by_label("Project title", exact=True).fill("Renamed by someone else")
        other.keyboard.press("Enter")
        expect(other.locator(".project-title")).to_have_text("Renamed by someone else")
        other.reload()  # make sure it was saved before the first browser edits
        expect(other.locator(".project-title")).to_have_text("Renamed by someone else")
    finally:
        other_context.close()

    pick_status(page, "On hold")  # this browser still holds the old version
    expect(page.get_by_role("status")).to_contain_text("Someone else changed this project")
    expect(page.locator(".project-title")).to_have_text("Renamed by someone else")  # reloaded
    expect(status_pill(page)).to_contain_text(PROGRESS)  # and its own change was not applied
