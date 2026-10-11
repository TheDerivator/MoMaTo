"""My timesheet in a real browser, as Anna Claes on the pinned Thursday 8 October 2026.
[TS-1] [TS-2] [TS-3] [TS-4] [TS-5] [TS-6] [TS-7] [TS-8] [TS-9] [TS-10] [TS-11] [TS-12] [TS-15]"""

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.conftest import remember, sign_in


def open_timesheet(
    page: Page,
    base: str,
    path: str = "timesheet",
    *,
    username: str = "anna.claes",
    wait_for: str | None = ".ts-card",
) -> None:
    remember(page)
    page.goto(f"{base}{path}")
    sign_in(page, username)
    if wait_for:
        expect(page.locator(wait_for).first).to_be_visible()


def card(page: Page, name: str) -> Locator:
    return page.locator(".ts-card").filter(has=page.locator(".ts-card__title", has_text=name))


def day_button(page: Page, label: str) -> Locator:
    return page.locator(".ts-day").filter(has=page.locator("b", has_text=label))


def plus(page: Page, name: str, times: int = 1) -> None:
    button = card(page, name).get_by_role("button", name=re.compile("^Add "))
    for _ in range(times):
        button.click()


def minus(page: Page, name: str, times: int = 1) -> None:
    button = card(page, name).get_by_role("button", name=re.compile("^Remove "))
    for _ in range(times):
        button.click()


def day_hours(page: Page, name: str) -> Locator:
    return card(page, name).locator(".ts-card__hours")


def week_card(page: Page) -> Locator:
    return page.locator(".week-card")


def saved(page: Page, action) -> None:
    """Run `action` and wait until the save request that follows it has been answered."""
    with page.expect_response(re.compile(r"/api/timesheet/.*/cells")) as response:
        action()
    assert response.value.ok, response.value.text()


# ---------------------------------------------------------------- the week as designed


def test_the_week_card_and_the_header_read_as_designed(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    expect(week_card(page).locator(".week-card__title")).to_have_text("Two days done!")
    expect(week_card(page).locator(".week-card__sub")).to_have_text(
        "16 of 40 h logged. Next up: Wednesday."
    )
    expect(week_card(page).locator(".week-card__hours")).to_have_text("16/40 h")
    expect(week_card(page).locator(".week-card__cta")).to_have_text("Keep going →")
    expect(page.locator(".ts-head__range")).to_have_text("Week 41 · 5 – 9 October 2026")
    expect(page.get_by_role("heading", level=1)).to_have_text("Two days done, 3 to go")
    expect(page.locator(".ts-ring__hours")).to_have_text("16")
    expect(page.locator(".ts-ring__of")).to_have_text("of 40 h")
    expect(page.locator(".ts-day")).to_have_count(5)
    expect(day_button(page, "Mon")).to_contain_text("8 / 8 h")
    expect(day_button(page, "Mon")).to_contain_text("✓")
    expect(day_button(page, "Thu")).to_contain_text("Today")
    expect(day_button(page, "Fri")).to_contain_text("Next")
    expect(day_button(page, "Thu")).to_have_attribute("aria-pressed", "true")  # today is selected
    expect(page.get_by_role("button", name="Submit week")).to_be_visible()


def test_the_cards_are_the_planned_projects_then_other_work_and_time_off(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server)
    titles = page.locator(".ts-card__title")
    expect(titles).to_have_text(
        [
            "Sensor retrofit on conveyor 4",
            "Vision-based quality check",
            "Predictive maintenance for pumps",
            "Digital shift handover",
            "Other work",
            "Time off",
        ]
    )
    sensors = card(page, "Sensor retrofit")
    expect(sensors.locator(".ts-card__sub")).to_have_text("#4102 · In progress")
    expect(sensors.locator(".ts-card__note")).to_have_text("7 h to go")
    expect(sensors.locator(".ts-card__week")).to_have_text("7 of 14 h this week")
    expect(sensors.locator("a.ts-card__title")).to_have_attribute("href", "projects/4102")
    expect(card(page, "Digital shift").locator(".ts-card__note")).to_have_text("4 h planned")
    expect(card(page, "Time off").locator(".ts-card__week")).to_have_text("0 h this week")
    expect(card(page, "Time off").locator(".ts-card__note")).to_have_text("0 h this week")
    # the task picker: running tasks, the next planned one, then General
    names = sensors.locator(".ts-task__name")
    expect(names).to_have_text(["Installation", "Commissioning", "General"])
    expect(sensors.locator(".ts-task--on .ts-task__name")).to_have_text("Installation")
    expect(sensors.locator(".ts-task__hours").first).to_have_text("7 h")
    expect(sensors.locator(".ts-card__goes")).to_have_text("goes to Installation")


# ---------------------------------------------------------------- booking


def test_plus_fills_the_card_and_updates_the_ring_bar_day_and_week_card(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server)
    saved(page, lambda: plus(page, "Sensor retrofit"))
    expect(day_hours(page, "Sensor retrofit")).to_have_text("1")
    expect(card(page, "Sensor retrofit").locator(".ts-card__note")).to_have_text("6 h to go")
    expect(card(page, "Sensor retrofit").locator(".ts-card__week")).to_have_text(
        "8 of 14 h this week"
    )
    expect(page.locator(".ts-ring__hours")).to_have_text("17")
    expect(day_button(page, "Thu")).to_contain_text("1 / 8 h")
    expect(week_card(page).locator(".week-card__hours")).to_have_text("17/40 h")
    expect(week_card(page).locator(".week-card__sub")).to_contain_text("17 of 40 h logged")
    fill = card(page, "Sensor retrofit").locator(".ts-card__fill")
    height = fill.evaluate(
        "el => el.getBoundingClientRect().height / el.parentElement.getBoundingClientRect().height"
    )
    assert 0.5 < height < 0.7  # 8 of 14 h
    # the saved state is what a reload shows
    page.reload()
    expect(day_hours(page, "Sensor retrofit")).to_have_text("1")


def test_plus_at_ten_hours_does_nothing(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    plus(page, "Digital shift", 10)
    expect(day_hours(page, "Digital shift")).to_have_text("10")
    plus(page, "Predictive", 1)  # the day already holds 10 h in total
    expect(day_hours(page, "Predictive")).to_have_text("0")
    plus(page, "Digital shift", 1)
    expect(day_hours(page, "Digital shift")).to_have_text("10")
    expect(page.locator(".ts-ring__hours")).to_have_text("26")


def test_minus_falls_back_to_another_task_with_time(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    sensors = card(page, "Sensor retrofit")
    sensors.get_by_role("button", name=re.compile("^Commissioning")).click()
    plus(page, "Sensor retrofit")
    expect(day_hours(page, "Sensor retrofit")).to_have_text("1")
    expect(
        sensors.locator(".ts-task", has_text="Commissioning").locator(".ts-task__hours")
    ).to_have_text("1 h")

    sensors.get_by_role("button", name=re.compile("^Installation")).click()  # no time on Thursday
    minus(page, "Sensor retrofit")
    expect(day_hours(page, "Sensor retrofit")).to_have_text("0")  # taken from Commissioning
    expect(
        sensors.locator(".ts-task", has_text="Commissioning").locator(".ts-task__hours")
    ).to_have_text("")
    minus(page, "Sensor retrofit")  # a line with no time that day: nothing happens
    expect(day_hours(page, "Sensor retrofit")).to_have_text("0")
    expect(page.locator(".ts-ring__hours")).to_have_text("16")


def test_the_selected_task_is_remembered(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    sensors = card(page, "Sensor retrofit")
    sensors.get_by_role("button", name=re.compile("^General")).click()
    expect(sensors.locator(".ts-card__goes")).to_have_text("goes to General")
    page.reload()
    expect(card(page, "Sensor retrofit").locator(".ts-card__goes")).to_have_text("goes to General")


def test_emptying_monday_turns_the_card_amber_and_vacation_fills_it_again(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server)
    day_button(page, "Mon").click()
    expect(day_button(page, "Mon")).to_have_attribute("aria-pressed", "true")
    minus(page, "Sensor retrofit", 3)
    minus(page, "Vision-based", 2)
    minus(page, "Predictive", 2)
    minus(page, "Other work", 1)
    expect(day_button(page, "Mon")).to_contain_text("0 / 8 h")
    expect(day_button(page, "Mon")).to_contain_text("Open")
    expect(week_card(page).locator(".week-card__title")).to_have_text("Monday still open")
    expect(week_card(page)).to_have_class(re.compile("week-card--open"))
    expect(week_card(page).locator(".week-card__cta")).to_have_text("Catch up →")
    expect(page.get_by_role("heading", level=1)).to_have_text("Let's catch up on Monday")

    vacation = card(page, "Time off")
    vacation.get_by_role("button", name=re.compile("^Vacation")).click()
    plus(page, "Time off", 8)
    expect(day_button(page, "Mon")).to_contain_text("8 / 8 h")
    expect(week_card(page).locator(".week-card__title")).to_have_text("Two days done!")


def test_a_full_week_says_so_and_can_be_submitted_with_a_celebration(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server)
    for label in ("Wed", "Thu", "Fri"):
        day_button(page, label).click()
        plus(page, "Digital shift", 8)
        expect(day_button(page, label)).to_contain_text("8 / 8 h")
    expect(week_card(page).locator(".week-card__title")).to_have_text("Full week done!")
    expect(week_card(page).locator(".week-card__cta")).to_have_text("Submit week →")
    expect(page.get_by_role("heading", level=1)).to_have_text("Your week is full. Ready to submit?")
    expect(page.locator(".ts-ring")).to_have_class(re.compile("ts-ring--full"))

    page.get_by_role("button", name="Submit week").click()
    modal = page.get_by_role("dialog")
    expect(modal).to_be_visible()
    expect(modal.get_by_role("heading")).to_have_text("Week 41 is in")
    expect(modal).to_contain_text("40 hours logged. ")
    expect(modal).to_contain_text("lines reached their planned hours.")
    expect(page.locator(".confetti__piece")).to_have_count(70)
    expect(modal.locator(".celebration__chip").first).to_contain_text("/")

    page.get_by_role("button", name="Back to work").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("button", name="Submitted ✓")).to_be_visible()
    expect(week_card(page).locator(".week-card__title")).to_have_text("Week 41 submitted ✓")
    expect(page.get_by_role("heading", level=1)).to_have_text("Week submitted")

    # changing time of a submitted week reopens it (TS-10)
    saved(page, lambda: minus(page, "Digital shift"))
    expect(page.get_by_role("button", name="Submit week")).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="Submit week")).to_be_visible()


def test_reduced_motion_shows_the_modal_without_confetti(sample_server: str, page: Page) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_timesheet(page, sample_server)
    page.get_by_role("button", name="Submit week").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.locator(".confetti__piece")).to_have_count(0)
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_with_the_switch_off_there_is_no_modal(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    page.get_by_role("button", name=re.compile(r"^Appearance and account of")).click()
    page.get_by_label("Celebrate submitted weeks").uncheck()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Submit week").click()
    expect(page.get_by_role("button", name="Submitted ✓")).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_ten_quick_clicks_end_in_the_right_total_after_a_reload(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server)
    button = card(page, "Sensor retrofit").get_by_role("button", name=re.compile("^Add "))
    for _ in range(10):
        button.click(delay=0)
    expect(day_hours(page, "Sensor retrofit")).to_have_text("10")
    page.reload()  # straight away: what was still waiting is sent as the page goes
    expect(day_hours(page, "Sensor retrofit")).to_have_text("10")
    expect(page.locator(".ts-ring__hours")).to_have_text("26")


def test_a_refused_save_rolls_back_with_a_message(sample_server: str, page: Page) -> None:
    """[SH-10] [TS-9] The count drops back and the reason is shown."""
    open_timesheet(page, sample_server)
    page.route(
        re.compile(r"/api/timesheet/.*/cells"),
        lambda route: route.fulfill(
            status=422,
            content_type="application/json",
            body='{"error": "rule_violation", "message": "a day holds at most 10 hours"}',
        ),
    )
    plus(page, "Sensor retrofit")
    expect(page.get_by_role("status")).to_contain_text("a day holds at most 10 hours")
    expect(day_hours(page, "Sensor retrofit")).to_have_text("0")
    expect(page.locator(".ts-ring__hours")).to_have_text("16")


# ---------------------------------------------------------------- weeks and projects


def test_other_weeks_can_be_visited_up_to_the_current_one(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    expect(page.get_by_role("link", name="Next week")).to_have_count(0)
    page.get_by_role("link", name="Previous week").click()
    expect(page).to_have_url(re.compile(r"/timesheet/2026-W40$"))
    expect(page.locator(".ts-head__range")).to_have_text("Week 40 · 28 September – 2 October 2026")
    expect(page.get_by_role("link", name="Next week")).to_be_visible()
    expect(page.get_by_role("link", name="This week")).to_be_visible()
    expect(day_button(page, "Mon")).to_have_attribute(
        "aria-pressed", "true"
    )  # Monday in a past week
    page.get_by_role("link", name="This week").click()
    expect(page).to_have_url(re.compile(r"/timesheet$"))


def test_a_future_week_is_not_open(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server, "timesheet/2026-W45", wait_for=None)
    expect(page.get_by_role("heading", name="That week is not open")).to_be_visible()


def test_a_project_can_be_added_and_stays_while_it_has_time(sample_server: str, page: Page) -> None:
    open_timesheet(page, sample_server)
    page.get_by_role("button", name="+ Add project").click()
    page.get_by_role("combobox", name="Find a project").fill("water reuse")
    page.get_by_role("option", name=re.compile("#4288")).click()
    added = card(page, "Water reuse")
    expect(added).to_be_visible()
    expect(added.locator(".ts-card__note")).to_have_text("Not planned")
    names = added.locator(".ts-task__name")
    expect(names.last).to_have_text("General")
    expect(names.first).to_have_text("Study & scoping")  # the project's tasks, then General
    saved(page, lambda: plus(page, "Water reuse"))
    expect(day_hours(page, "Water reuse")).to_have_text("1")
    page.reload()
    expect(card(page, "Water reuse")).to_be_visible()  # it has time this week: it stays
    saved(page, lambda: minus(page, "Water reuse"))
    page.reload()
    expect(card(page, "Water reuse")).to_have_count(0)  # no time any more: it is gone


def test_the_week_card_opens_the_timesheet_and_the_rail_has_a_mini_ring(
    sample_server: str, page: Page
) -> None:
    open_timesheet(page, sample_server, "projects", wait_for=".table__link")
    week_card(page).click()
    expect(page).to_have_url(re.compile(r"/timesheet$"))
    page.get_by_role("button", name="Collapse menu").click()
    rail = page.locator(".week-rail")
    expect(rail).to_be_visible()
    expect(rail.locator(".week-rail__hours")).to_have_text("16")
    expect(rail.locator(".week-rail__bar")).to_have_count(5)


# ---------------------------------------------------------------- phone width


def test_at_phone_width_the_cards_stack_and_plus_and_submit_work(
    sample_server: str, page: Page
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    open_timesheet(page, sample_server)
    x_positions = {
        round(box["x"])
        for c in page.locator(".ts-card").all()
        if (box := c.bounding_box()) is not None
    }
    assert len(x_positions) == 1  # one column
    scrolls = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert scrolls is False
    saved(page, lambda: plus(page, "Sensor retrofit"))
    expect(day_hours(page, "Sensor retrofit")).to_have_text("1")
    day_button(page, "Wed").click()
    expect(day_button(page, "Wed")).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="Submit week").click()
    expect(page.get_by_role("button", name="Submitted ✓")).to_be_visible()
    page.get_by_role("button", name="Back to work").click()


# ---------------------------------------------------------------- who has a timesheet


def test_a_system_account_has_no_week_card(sample_server: str, page: Page) -> None:
    from tests.conftest import TEST_ADMIN_PASSWORD

    remember(page)
    page.goto(f"{sample_server}projects")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.locator(".table__link").first).to_be_visible()
    expect(page.locator(".week-card")).to_have_count(0)
