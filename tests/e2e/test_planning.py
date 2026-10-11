"""The Planning and People & days tabs in a real browser: the gantt, the task dialog, cells and
people. [PG-1] [PG-2] [PG-3] [PG-4] [PG-5] [PD-1] [PD-2] [PD-3] [PD-4] [PD-5] [OV-2] [OV-5]"""

import re
from collections import defaultdict
from decimal import Decimal

from playwright.sync_api import Locator, Page, expect

from momato.services.sample_data import Sample
from tests.e2e.conftest import remember, sign_in

SENSORS = 4102
TASKS = [
    "Study & scoping",
    "Supplier offers",
    "Order & delivery",
    "Installation",
    "Commissioning",
    "Handover & close-out",
]


def open_tab(
    page: Page, base: str, tab: str, *, username: str = "tomas.rivera", number: int = SENSORS
) -> None:
    remember(page)
    page.goto(f"{base}projects/{number}/{tab}")
    sign_in(page, username)
    expect(page.locator(".project-title")).to_be_visible()


def task_rows(page: Page) -> Locator:
    return page.locator(".gantt__task")


def task(page: Page, name: str) -> Locator:
    return task_rows(page).filter(has=page.locator(".gantt__name", has_text=name))


def tab_link(page: Page, name: str) -> Locator:
    return page.get_by_role("navigation", name="Project sections").get_by_role(
        "link", name=re.compile(f"^{re.escape(name)}")
    )


def hue_of(page: Page, name: str) -> str:
    """The colour hue a task's lane was given (PG-3)."""
    lane = task(page, name).locator(".gantt__lane")
    return lane.evaluate("el => getComputedStyle(el).getPropertyValue('--hue').trim()")


def fill_task(page: Page, **values: str) -> None:
    dialog = page.get_by_role("dialog", name=re.compile("task$"))
    labels = {
        "name": "Name",
        "start": "Planned start",
        "end": "Planned end",
        "revised": "Revised end (optional)",
        "progress": "Progress (%)",
    }
    for key, value in values.items():
        dialog.get_by_label(labels[key], exact=True).fill(value)


# ---------------------------------------------------------------- the gantt


def test_the_gantt_shows_the_tasks_on_a_quarter_axis_with_today(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "planning")
    expect(page.locator(".gantt__count")).to_have_text("6 tasks")
    expect(page.locator(".gantt__name")).to_have_text(TASKS)
    expect(page.locator(".gantt__quarter")).to_have_text(
        ["Q4/25", "Q1/26", "Q2/26", "Q3/26", "Q4/26", "Q1/27"]
    )
    expect(page.locator(".gantt__quarter--now")).to_have_text("Q4/26")
    expect(page.locator(".gantt__today-pill")).to_have_text("Today")
    expect(page.locator(".gantt__today")).to_have_count(6)  # the line runs through every row
    expect(task(page, "Installation").locator(".gantt__sub")).to_have_text(
        "17 Jun – 19 Nov · Running · slipped"
    )
    expect(task(page, "Study & scoping").locator(".gantt__sub")).to_have_text(
        "3 Nov – 14 Jan · Done"
    )
    expect(task(page, "Commissioning").locator(".gantt__sub")).to_have_text(
        "28 Oct – 18 Jan · Planned · milestone"
    )
    for legend in ("Planned", "Progress", "Revised end", "Milestone"):
        expect(page.locator(".legend")).to_contain_text(legend)


def test_bars_are_coloured_by_status_and_the_slipped_one_has_an_extension(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "planning")
    assert hue_of(page, "Study & scoping") == "155"  # Done
    assert hue_of(page, "Installation") == "285"  # Running
    assert hue_of(page, "Commissioning") == "235"  # Planned
    expect(page.locator(".gantt__extension")).to_have_count(1)
    expect(task(page, "Installation").locator(".gantt__extension")).to_have_count(1)
    expect(task(page, "Order & delivery").locator(".gantt__milestone")).to_have_count(1)
    expect(page.locator(".gantt__milestone")).to_have_count(2)
    fill = task(page, "Installation").locator(".gantt__fill")
    width = fill.evaluate(
        "el => el.getBoundingClientRect().width / el.parentElement.getBoundingClientRect().width"
    )
    assert 0.5 < width < 1  # 65 % of a 5-month task measured against its revised end


def test_today_is_left_out_when_it_is_outside_the_axis(
    sample_server: str, page: Page, sample: Sample
) -> None:
    finished = next(
        p
        for p in sample.projects
        if p.end < sample.today and p.status.value == "finished" and p.tasks
    )
    open_tab(page, sample_server, "planning", number=finished.number)
    expect(page.locator(".gantt__task").first).to_be_visible()
    expect(page.locator(".gantt__today-pill")).to_have_count(0)
    expect(page.locator(".gantt__today")).to_have_count(0)


def test_a_viewer_sees_the_gantt_without_editing(sample_server: str, page: Page) -> None:
    open_tab(page, sample_server, "planning", username="bram.peeters")
    expect(page.locator(".gantt__name")).to_have_text(TASKS)
    expect(page.get_by_role("button", name="+ Add task")).to_have_count(0)
    expect(page.locator(".gantt__name--button")).to_have_count(0)


# ---------------------------------------------------------------- the task dialog


def test_a_new_task_at_100_percent_is_done_and_where_we_are_says_so(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "planning")
    page.get_by_role("button", name="+ Add task").click()
    fill_task(page, name="Pilot run", start="2026-11-02", end="2026-11-30", progress="100")
    page.get_by_role("dialog", name="Add task").get_by_role("button", name="Add task").click()

    expect(page.locator(".gantt__count")).to_have_text("7 tasks")
    row = task(page, "Pilot run")
    expect(row.locator(".gantt__sub")).to_have_text("2 Nov – 30 Nov · Done")
    assert hue_of(page, "Pilot run") == "155"

    tab_link(page, "Overview").click()
    phase = page.locator(".phase", has_text="Pilot run")
    expect(phase.locator(".phase__status")).to_have_text("Done")


def test_a_revised_end_draws_the_dashed_extension_and_says_slipped(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "planning")
    before = page.locator(".gantt__extension").count()
    task(page, "Commissioning").locator(".gantt__name").click()
    fill_task(page, revised="2027-02-26")
    page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Save").click()
    expect(page.locator(".gantt__extension")).to_have_count(before + 1)
    expect(task(page, "Commissioning").locator(".gantt__sub")).to_have_text(
        "28 Oct – 26 Feb · Planned · slipped · milestone"
    )
    # and it can be taken away again
    task(page, "Commissioning").locator(".gantt__name").click()
    fill_task(page, revised="")
    page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Save").click()
    expect(page.locator(".gantt__extension")).to_have_count(before)


def test_dates_that_make_no_sense_are_refused_in_the_dialog(sample_server: str, page: Page) -> None:
    open_tab(page, sample_server, "planning")
    page.get_by_role("button", name="+ Add task").click()
    fill_task(page, name="Backwards", start="2026-12-01", end="2026-11-01")
    dialog = page.get_by_role("dialog", name="Add task")
    dialog.get_by_role("button", name="Add task").click()
    expect(dialog.get_by_role("alert")).to_contain_text("cannot be before its start")
    fill_task(page, start="2026-11-01", end="2026-12-01", revised="2026-12-01")
    dialog.get_by_role("button", name="Add task").click()
    expect(dialog.get_by_role("alert")).to_contain_text("revised end must be after")
    expect(task_rows(page)).to_have_count(6)


def test_tasks_move_up_and_down(sample_server: str, page: Page) -> None:
    open_tab(page, sample_server, "planning")
    task(page, "Supplier offers").locator(".gantt__name").click()
    dialog = page.get_by_role("dialog", name="Edit task")
    dialog.get_by_role("button", name="Move down").click()
    expect(page.locator(".gantt__name")).to_have_text(
        [
            "Study & scoping",
            "Order & delivery",
            "Supplier offers",
            "Installation",
            "Commissioning",
            "Handover & close-out",
        ]
    )
    task(page, "Study & scoping").locator(".gantt__name").click()
    expect(
        page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Move up")
    ).to_be_disabled()
    page.keyboard.press("Escape")
    page.reload()
    expect(page.locator(".gantt__name").nth(1)).to_have_text("Order & delivery")


def test_deleting_a_task_with_hours_asks_first_and_says_where_they_go(
    sample_server: str, page: Page, sample: Sample
) -> None:
    spec = next(p for p in sample.projects if p.number == SENSORS)
    booked: dict[int | None, int] = defaultdict(int)
    for entry in sample.entries:
        if entry.project == SENSORS:
            booked[entry.task] += entry.minutes
    index = TASKS.index("Study & scoping")
    hours = booked[index] / 60
    assert hours > 0 and spec.tasks[index].name == "Study & scoping"

    open_tab(page, sample_server, "planning")
    task(page, "Study & scoping").locator(".gantt__name").click()
    page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Delete").click()
    confirm = page.get_by_role("dialog", name="Delete this task?")
    expect(confirm).to_contain_text(f"{hours:g} h booked on “Study & scoping” move to General.")
    confirm.get_by_role("button", name="Cancel").click()
    expect(task_rows(page)).to_have_count(6)

    page.get_by_role("dialog", name="Edit task").get_by_role("button", name="Delete").click()
    page.get_by_role("dialog", name="Delete this task?").get_by_role(
        "button", name="Delete task"
    ).click()
    expect(task_rows(page)).to_have_count(5)
    expect(page.get_by_role("dialog")).to_have_count(0)
    # the hours were not lost: the project's logged days are unchanged
    tab_link(page, "Overview").click()
    expect(page.locator(".days__number")).to_be_visible()


# ---------------------------------------------------------------- people & days


def planned_total(sample: Sample) -> Decimal:
    spec = next(p for p in sample.projects if p.number == SENSORS)
    return sum(spec.planned.values(), Decimal(0))


def row(page: Page, name: str) -> Locator:
    return page.locator(".people-days__row").filter(
        has=page.locator(".days-person__name", has_text=name)
    )


def test_the_grid_has_a_row_per_member_a_column_per_quarter_and_a_total(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "people")
    expect(page.locator(".days-person__name")).to_have_text(
        ["Tomás Rivera", "Anna Claes", "Pieter Kools", "Sofia Lind"]
    )
    expect(row(page, "Tomás Rivera").locator(".days-person__tag")).to_have_text("Coordinator")
    expect(row(page, "Anna Claes").locator(".days-person__tag")).to_have_text("Quality engineer")
    head = page.locator(".people-days__row--head")
    expect(head).to_contain_text("Q4/25")
    expect(head).to_contain_text("Q1/27")
    expect(head.locator(".days-head--now")).to_have_text("Q4/26")
    anna = row(page, "Anna Claes")
    expect(anna.locator(".days-cell__value").nth(4)).to_have_text("23 d")  # Q4/26
    expect(anna.locator(".days-cell__sub").nth(5)).to_have_text("upcoming")  # Q1/27
    expect(anna.locator(".days-total__value")).to_have_text("60.5 d")
    expect(page.get_by_text("Number: planned days. Bar: days logged against them.")).to_be_visible()


def test_setting_a_cell_updates_the_row_total_and_the_days_card_and_survives_a_reload(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_tab(page, sample_server, "people")
    anna = row(page, "Anna Claes")
    cell = anna.locator(".days-cell").nth(5)  # Q1/27: 3.5 d
    cell.get_by_role("button").click()
    field = page.get_by_label("Planned days for Anna Claes in Q1/27")
    field.fill("12.5")
    field.press("Enter")
    expect(cell.locator(".days-cell__value")).to_have_text("12.5 d")
    expect(anna.locator(".days-total__value")).to_have_text("69.5 d")

    expected = planned_total(sample) + Decimal("9")  # 12.5 instead of 3.5
    tab_link(page, "Overview").click()
    expect(page.locator(".days__figure")).to_contain_text(f"of {expected} planned days logged")

    page.reload()
    tab_link(page, "People & days").click()
    expect(row(page, "Anna Claes").locator(".days-cell__value").nth(5)).to_have_text("12.5 d")


def test_escape_cancels_and_a_bad_value_is_refused_with_a_message(
    sample_server: str, page: Page
) -> None:
    open_tab(page, sample_server, "people")
    cell = row(page, "Anna Claes").locator(".days-cell").nth(5)
    cell.get_by_role("button").click()
    field = page.get_by_label("Planned days for Anna Claes in Q1/27")
    field.fill("20")
    field.press("Escape")
    expect(cell.locator(".days-cell__value")).to_have_text("3.5 d")

    cell.get_by_role("button").click()
    field = page.get_by_label("Planned days for Anna Claes in Q1/27")
    field.fill("12.3")
    field.press("Enter")
    expect(page.get_by_role("status")).to_contain_text("steps of 0.5")
    expect(cell.locator(".days-cell__value")).to_have_text("3.5 d")

    cell.get_by_role("button").click()
    field = page.get_by_label("Planned days for Anna Claes in Q1/27")
    field.fill("90")
    field.press("Enter")
    expect(page.get_by_role("status")).to_contain_text("working days")


def test_a_cell_can_be_cleared(sample_server: str, page: Page) -> None:
    open_tab(page, sample_server, "people")
    cell = row(page, "Anna Claes").locator(".days-cell").nth(5)
    cell.get_by_role("button").click()
    field = page.get_by_label("Planned days for Anna Claes in Q1/27")
    field.fill("")
    field.press("Enter")
    expect(cell.locator(".days-cell__value")).to_have_text("–")
    expect(row(page, "Anna Claes").locator(".days-total__value")).to_have_text("57 d")


def test_adding_a_person_adds_a_row_and_a_chip_and_removing_asks_first(
    sample_server: str, page: Page, sample: Sample
) -> None:
    open_tab(page, sample_server, "people")
    page.get_by_role("button", name="+ Add person").click()
    page.get_by_role("combobox", name="Add a person").fill("bram")
    page.get_by_role("option", name=re.compile("Bram Peeters")).click()
    expect(row(page, "Bram Peeters")).to_be_visible()
    expect(row(page, "Bram Peeters").locator(".days-total__value")).to_have_text("–")
    tab_link(page, "Overview").click()
    expect(page.locator(".person-chip", has_text="Bram Peeters")).to_be_visible()

    tab_link(page, "People & days").click()
    sofia = row(page, "Sofia Lind")
    expect(sofia.locator(".days-total__value")).to_have_text("39 d")
    page.get_by_role("button", name="Remove Sofia Lind").click()
    dialog = page.get_by_role("dialog", name="Remove Sofia Lind?")
    expect(dialog).to_contain_text("planned days on it are removed")
    dialog.get_by_role("button", name="Cancel").click()
    expect(sofia).to_be_visible()

    page.get_by_role("button", name="Remove Sofia Lind").click()
    page.get_by_role("dialog", name="Remove Sofia Lind?").get_by_role(
        "button", name="Remove"
    ).click()
    members = page.locator(".people-days__table > .people-days__row .days-person__name")
    expect(members).to_have_text(["Tomás Rivera", "Anna Claes", "Bram Peeters", "Pieter Kools"])
    # her planned days are gone from the project
    expected = planned_total(sample) - Decimal("39")
    tab_link(page, "Overview").click()
    expect(page.locator(".days__figure")).to_contain_text(f"of {expected} planned days logged")
    # but the hours she booked stay: shown under "Also booked"
    tab_link(page, "People & days").click()
    also = page.locator(".people-days__also")
    expect(also).to_contain_text("Also booked")
    expect(also.locator(".days-person__name")).to_have_text(["Sofia Lind"])


def test_a_viewer_cannot_edit_the_grid(sample_server: str, page: Page) -> None:
    open_tab(page, sample_server, "people", username="bram.peeters")
    expect(page.locator(".days-person__name").first).to_be_visible()
    expect(page.get_by_role("button", name="+ Add person")).to_have_count(0)
    expect(page.locator(".days-cell button")).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("^Remove "))).to_have_count(0)
