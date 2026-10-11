"""Administration and the Profile page in a real browser, as the built-in administrator and as
Anna Claes. [ADM-1] [ADM-2] [ADM-3] [ADM-4] [ADM-5] [ADM-6] [ADM-8] [AUTH-4] [AUTH-5]"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx2
from playwright.sync_api import Browser, Locator, Page, expect

from momato.services.sample_data import Sample
from tests.conftest import DEMO_PASSWORD, TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in


def open_admin(
    page: Page,
    base: str,
    section: str = "",
    *,
    username: str = "admin",
    password: str = TEST_ADMIN_PASSWORD,
) -> None:
    remember(page)
    page.goto(f"{base}admin/{section}")
    sign_in(page, username, password)
    expect(page.locator(".admin-page")).to_be_visible()


def api_json(base: str, page: Page, path: str) -> Any:
    cookies = {c.get("name", ""): c.get("value", "") for c in page.context.cookies()}
    response = httpx2.get(f"{base}api/{path}", cookies=cookies)
    assert response.status_code == 200, response.text
    return response.json()


@contextmanager
def second_browser(
    browser: Browser, base: str, path: str, username: str, ready: str
) -> Iterator[Page]:
    """Another person in another browser, signed in and showing `path`."""
    context = browser.new_context()
    try:
        page = context.new_page()
        remember(page)
        page.goto(f"{base}{path}")
        sign_in(page, username)
        expect(page.locator(ready).first).to_be_visible()
        yield page
    finally:
        context.close()


def toast(page: Page, text: str) -> Locator:
    """The toast saying `text` (several can be on screen at once)."""
    return page.locator(".toast").filter(has_text=text).first


def org_row(page: Page, name: str) -> Locator:
    return page.locator(".org-row").filter(has=page.get_by_label(f"Name of {name}", exact=True))


def person_with_no_override(base: str, page: Page) -> dict[str, Any]:
    """Someone whose availability of 2026 is the default, and who can sign in."""
    people = api_json(base, page, "admin/people")
    return next(
        p
        for p in people
        if p["username"]
        and p["status"] == "active"
        and next(a for a in p["availability"] if a["year"] == 2026)["override_days"] is None
    )


# ---------------------------------------------------------------- who sees it


def test_administration_is_offered_to_administrators_only(sample_server: str, page: Page) -> None:
    remember(page)
    page.goto(f"{sample_server}projects")
    sign_in(page, "anna.claes")
    page.get_by_role("button", name=re.compile(r"^Appearance and account of")).click()
    expect(page.get_by_role("link", name="Profile")).to_be_visible()
    expect(page.get_by_role("link", name="Administration")).to_have_count(0)
    page.keyboard.press("Escape")
    page.goto(f"{sample_server}admin")
    expect(page.get_by_role("heading", name="No administration rights")).to_be_visible()
    expect(page.get_by_role("navigation", name="Administration sections")).to_have_count(0)


def test_an_administrator_finds_every_section_from_the_account_menu(
    sample_server: str, page: Page
) -> None:
    remember(page)
    page.goto(f"{sample_server}projects")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name=re.compile(r"^Appearance and account of")).click()
    page.get_by_role("link", name="Administration").click()
    expect(page).to_have_url(re.compile(r"/admin$"))
    tabs = page.get_by_role("navigation", name="Administration sections").get_by_role("link")
    expect(tabs).to_have_text(
        ["Organisation", "People", "Roles", "Default access", "Single sign-on", "Audit log"]
    )
    expect(page.get_by_role("heading", level=1)).to_have_text("Organisation")
    tabs.filter(has_text="Audit log").click()
    expect(page).to_have_url(re.compile(r"/admin/audit$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Audit log")


# ---------------------------------------------------------------- the org tree (ADM-1)


def test_the_org_tree_is_edited_branch_by_branch(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "org")
    nodes = api_json(sample_server, page, "admin/org")
    stl = next(n["id"] for n in nodes if n["name"] == "STL")

    # add
    org_row(page, "STL").get_by_role("button", name="+ Branch").click()
    page.get_by_label("New branch under STL").fill("Metrology")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(org_row(page, "Metrology")).to_be_visible()
    expect(toast(page, "Added Metrology")).to_be_visible()

    # rename
    field = page.get_by_label("Name of Metrology", exact=True)
    field.fill("Metrology lab")
    field.press("Enter")
    expect(org_row(page, "Metrology lab")).to_be_visible()

    # flag as a department
    flag = org_row(page, "Metrology lab").get_by_role("checkbox", name="Department")
    flag.check()
    expect(flag).to_be_checked()
    page.reload()
    expect(
        org_row(page, "Metrology lab").get_by_role("checkbox", name="Department")
    ).to_be_checked()

    # move under R&D
    org_row(page, "Metrology lab").get_by_label("Move Metrology lab under").select_option(
        label="– R&D"
    )
    expect(toast(page, "Moved Metrology lab")).to_be_visible()
    moved = next(
        n for n in api_json(sample_server, page, "admin/org") if n["name"] == "Metrology lab"
    )
    parent = next(
        n for n in api_json(sample_server, page, "admin/org") if n["id"] == moved["parent_id"]
    )
    assert parent["name"] == "R&D"
    assert stl != moved["parent_id"]

    # reorder: one place up among the children of R&D
    org_row(page, "Metrology lab").get_by_role("button", name="Move Metrology lab up").click()
    expect(
        org_row(page, "Metrology lab").get_by_role("button", name="Move Metrology lab down")
    ).to_be_enabled()
    nodes = api_json(sample_server, page, "admin/org")
    siblings = sorted(
        (n for n in nodes if n["parent_id"] == parent["id"]), key=lambda n: n["position"]
    )
    assert [n["name"] for n in siblings] == [
        "Coatings",
        "Metallurgy",
        "Metrology lab",
        "Process modelling",
    ]

    # delete
    org_row(page, "Metrology lab").get_by_role("button", name="Delete Metrology lab").click()
    page.get_by_role("dialog").get_by_role("button", name="Delete branch").click()
    expect(org_row(page, "Metrology lab")).to_have_count(0)


def test_a_branch_in_use_is_not_deleted_and_says_why(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "org")
    org_row(page, "Quality").get_by_role("button", name="Delete Quality").click()
    page.get_by_role("dialog").get_by_role("button", name="Delete branch").click()
    expect(toast(page, "still used by")).to_be_visible()
    expect(toast(page, "people")).to_be_visible()
    expect(org_row(page, "Quality")).to_be_visible()
    # the root has no delete button, and cannot be moved
    expect(
        org_row(page, "Brightwater Industries").get_by_role("button", name=re.compile("Delete"))
    ).to_have_count(0)


def test_flagging_a_department_changes_who_sees_whose_time(
    browser: Browser, sample_server: str, page: Page
) -> None:
    """[ADM-1] [D-006] [D-013] Time is visible inside the viewer's own department."""
    rows = ".pp-person"
    with second_browser(
        browser, sample_server, "people?mode=spent&period=month", "anna.claes", rows
    ) as anna:
        expect(anna.locator(rows)).to_have_count(11)  # all of STL

        open_admin(page, sample_server, "org")
        stl = org_row(page, "STL").get_by_role("checkbox", name="Department")
        stl.uncheck()
        expect(stl).not_to_be_checked()
        anna.reload()
        expect(anna.locator(rows)).to_have_count(1)  # only her own time: she has no department
        expect(anna.get_by_role("note")).to_have_text(
            "69 people in this branch whose hours you can't see."
        )

        quality = org_row(page, "Quality").get_by_role("checkbox", name="Department")
        quality.check()
        expect(quality).to_be_checked()
        in_quality = [
            p
            for p in api_json(sample_server, page, "admin/people")
            if p["org_node_id"]
            == next(
                n["id"]
                for n in api_json(sample_server, page, "admin/org")
                if n["name"] == "Quality"
            )
        ]
        anna.reload()
        expect(anna.locator(rows)).to_have_count(len(in_quality))
        assert 1 < len(in_quality) < 11


# ---------------------------------------------------------------- people (ADM-2 – ADM-5)


def test_the_people_list_filters_and_opens_a_person(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "people")
    expect(page.locator(".admin-person")).to_have_count(70)
    page.get_by_label("Find").fill("bram.peeters")
    expect(page.locator(".admin-person")).to_have_count(1)
    page.get_by_role("link", name="Bram Peeters").click()
    expect(page).to_have_url(re.compile(r"/admin/people/\d+$"))
    expect(page.get_by_role("heading", name="Bram Peeters")).to_be_visible()
    expect(page.get_by_label("Name", exact=True)).to_have_value("Bram Peeters")
    expect(page.get_by_label("Username")).to_have_value("bram.peeters")
    page.get_by_role("link", name="← People").click()
    expect(page.locator(".admin-person").first).to_be_visible()


def test_a_new_person_gets_a_sign_in_and_signs_in_with_the_generated_password(
    browser: Browser, sample_server: str, page: Page
) -> None:
    open_admin(page, sample_server, "people")
    page.get_by_role("button", name="+ New person").click()
    dialog = page.get_by_role("dialog", name="New person")
    dialog.get_by_label("Name", exact=True).fill("Nora Vandamme")
    dialog.get_by_label("Job title").fill("Metrology engineer")
    dialog.get_by_label("Place in the organisation").select_option(label="– – Quality")
    dialog.get_by_label("Hours on Fri").fill("4")
    dialog.get_by_role("button", name="Add person").click()
    expect(page).to_have_url(re.compile(r"/admin/people/\d+$"))
    expect(page.get_by_role("heading", name="Nora Vandamme")).to_be_visible()
    expect(page.get_by_label("Hours on Fri")).to_have_value("4")

    # no sign-in yet: prepare one
    expect(page.get_by_role("button", name="Generate a new password")).to_be_disabled()
    page.get_by_role("button", name="Suggest").click()
    expect(page.get_by_label("Username")).to_have_value("nora.vandamme")
    page.get_by_role("button", name="Save sign-in").click()
    expect(toast(page, "Sign-in saved")).to_be_visible()
    page.get_by_role("button", name="Generate a new password").click()
    secret = page.locator(".admin-secret__value")
    expect(secret).to_be_visible()
    password = secret.inner_text()
    assert len(password) >= 10

    context = browser.new_context()
    try:
        other = context.new_page()
        remember(other)
        other.goto(f"{sample_server}timesheet")
        sign_in_dialog = other.get_by_role("dialog", name="Log in")
        sign_in_dialog.get_by_label("Username").fill("nora.vandamme")
        sign_in_dialog.get_by_label("Password").fill(password)
        sign_in_dialog.get_by_role("button", name="Log in").click()
        # a password set by an administrator must be changed before anything else
        expect(other.get_by_role("dialog", name="Choose a new password")).to_be_visible()
    finally:
        context.close()


def test_suspending_a_person_ends_their_open_session(
    browser: Browser, sample_server: str, page: Page
) -> None:
    """[ADM-3] [AUTH-4]"""
    with second_browser(browser, sample_server, "timesheet", "bram.peeters", ".ts-card") as bram:
        open_admin(page, sample_server, "people")
        page.get_by_label("Find").fill("bram.peeters")
        page.get_by_role("link", name="Bram Peeters").click()
        page.get_by_role("button", name="Suspend sign-in").click()
        page.get_by_role("dialog").get_by_role("button", name="Suspend sign-in").click()
        expect(page.locator(".admin-person-head .admin-status")).to_have_text("Sign-in suspended")

        bram.reload()  # the next request finds the session gone
        expect(bram.get_by_role("dialog", name="Log in")).to_be_visible()
        dialog = bram.get_by_role("dialog", name="Log in")
        dialog.get_by_label("Username").fill("bram.peeters")
        dialog.get_by_label("Password").fill(DEMO_PASSWORD)
        dialog.get_by_role("button", name="Log in").click()
        expect(dialog.get_by_role("alert")).to_be_visible()  # refused while suspended

        page.get_by_role("button", name="Restore sign-in").click()
        expect(page.locator(".admin-person-head .admin-status")).to_have_text("Active")
        dialog.get_by_role("button", name="Log in").click()
        dialog.wait_for(state="detached")


def test_a_work_pattern_changes_timesheet_targets_and_planning_capacity(
    browser: Browser, sample_server: str, page: Page
) -> None:
    """[ADM-2] [D-019] [D-020] A four-day week: no Friday target, 4/5 of the standard days."""
    open_admin(page, sample_server, "people")
    chosen = person_with_no_override(sample_server, page)
    before = api_json(sample_server, page, f"admin/people/{chosen['id']}")
    standard = next(a for a in before["availability"] if a["year"] == 2026)["default_days"]

    page.goto(f"{sample_server}admin/people/{chosen['id']}")
    expect(page.get_by_label("Hours on Fri")).to_have_value("8")
    page.get_by_label("Hours on Fri").fill("0")
    page.get_by_role("button", name="Save details").click()
    expect(toast(page, "Saved")).to_be_visible()
    row = page.locator(".admin-table--compact tbody tr").filter(has_text="2026")
    expect(row).to_contain_text(f"{standard * 4 / 5:g} d")  # the default follows the pattern

    plan = api_json(sample_server, page, f"people-planning?q={chosen['name']}")
    free_after = plan["rows"][0]["total"]["free"]
    assert free_after is not None

    with second_browser(
        browser, sample_server, "timesheet", chosen["username"], ".ts-card, .ts-empty, .ts-day"
    ) as person:
        week = api_json(sample_server, person, "timesheet")
        assert [d["target_minutes"] for d in week["days"]] == [480, 480, 480, 480, 0]


def test_an_availability_override_shows_on_people_planning(sample_server: str, page: Page) -> None:
    """[ADM-4] [D-020]"""
    open_admin(page, sample_server, "people")
    chosen = person_with_no_override(sample_server, page)
    page.goto(f"{sample_server}admin/people/{chosen['id']}")
    page.get_by_label("Days available in 2026").fill("100")
    page.get_by_role("button", name="Set", exact=True).first.click()
    row = page.locator(".admin-table--compact tbody tr").filter(has_text="2026")
    expect(row).to_contain_text("100 d")
    expect(row).to_contain_text("(override)")

    page.goto(f"{sample_server}people?person={chosen['id']}")
    person = page.locator(".pp-person").filter(
        has=page.locator(".pp-person__name", has_text=chosen["name"])
    )
    expect(person).to_be_visible()
    plan = api_json(sample_server, page, f"people-planning?q={chosen['name']}")
    total = plan["rows"][0]["total"]
    assert abs(total["free"] - (100 - total["value"])) < 0.01
    expect(person.locator(".pp-total__sub")).to_contain_text("free")

    page.goto(f"{sample_server}admin/people/{chosen['id']}")
    page.get_by_role("button", name="Clear the override of 2026").click()
    expect(
        page.locator(".admin-table--compact tbody tr").filter(has_text="2026")
    ).not_to_contain_text("(override)")


def test_a_deactivated_person_leaves_the_pickers_but_keeps_their_history(
    sample_server: str, page: Page, sample: Sample
) -> None:
    """[ADM-2]"""
    open_admin(page, sample_server, "people")
    bram = next(
        p for p in api_json(sample_server, page, "admin/people") if p["name"] == "Bram Peeters"
    )
    with_bram = next(p.number for p in sample.projects if "Bram Peeters" in p.members)

    page.goto(f"{sample_server}admin/people/{bram['id']}")
    page.get_by_role("button", name="Deactivate").click()
    page.get_by_role("dialog").get_by_role("button", name="Deactivate").click()
    expect(page.locator(".admin-person-head .admin-status")).to_have_text("Deactivated")
    expect(page.get_by_role("button", name="Reactivate")).to_be_visible()

    # the list hides them until asked
    page.get_by_role("link", name="← People").click()
    expect(page.locator(".admin-person").first).to_be_visible()
    expect(page.locator(".admin-person__name", has_text="Bram Peeters")).to_have_count(0)
    page.get_by_label("Show deactivated people").check()
    expect(page.locator(".admin-person__name", has_text="Bram Peeters")).to_be_visible()

    # not offered when choosing a person ...
    page.goto(f"{sample_server}projects")
    page.get_by_role("button", name="+ New project").click()
    dialog = page.get_by_role("dialog", name="New project")
    dialog.get_by_label("Coordinator").fill("Bram")
    expect(dialog.get_by_role("listbox", name="Coordinator results")).to_contain_text(
        "No one found"
    )
    page.keyboard.press("Escape")
    # ... nor in people planning, but their history is still there
    page.goto(f"{sample_server}people")
    expect(page.locator(".pp-person").first).to_be_visible()
    page.get_by_label("Filter by person").fill("Bram")
    expect(page.locator(".pp-person")).to_have_count(0)
    page.goto(f"{sample_server}projects/{with_bram}/people")
    expect(page.locator(".people-days")).to_contain_text("Bram Peeters")


def test_access_is_granted_on_a_branch_and_removed(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "people")
    anna = next(
        p for p in api_json(sample_server, page, "admin/people") if p["name"] == "Anna Claes"
    )
    page.goto(f"{sample_server}admin/people/{anna['id']}")
    access = page.get_by_role("region", name="Access")
    expect(access).to_contain_text("No roles of their own")
    access.get_by_label("Role").select_option(label="Project administrator")
    access.get_by_label("Where").select_option(label="STL")
    access.get_by_role("button", name="Grant").click()
    expect(access).to_contain_text("Project administrator · STL")
    access.get_by_role("button", name="Remove Project administrator (STL)").click()
    expect(access).to_contain_text("No roles of their own")


# ---------------------------------------------------------------- roles and default access (ADM-5)


def test_a_custom_role_is_created_edited_and_deleted(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "roles")
    expect(page.get_by_role("region", name="Role Viewer")).to_contain_text("Built in")
    expect(
        page.get_by_role("region", name="Role Viewer").get_by_role(
            "checkbox", name=re.compile("^project.view")
        )
    ).to_be_disabled()

    form = page.get_by_role("form", name="New role")
    form.get_by_label("Name", exact=True).fill("Plan keeper")
    expect(form.get_by_label("Key")).to_have_value("plan_keeper")
    form.get_by_role("checkbox", name=re.compile("^plan.manage")).check()
    form.get_by_role("button", name="Create role").click()
    role = page.get_by_role("region", name="Role Plan keeper")
    expect(role).to_be_visible()
    expect(role.get_by_role("checkbox", name=re.compile("^plan.manage"))).to_be_checked()

    role.get_by_role("checkbox", name=re.compile("^hours.view")).check()
    role.get_by_role("button", name="Save role").click()
    expect(toast(page, "Role saved")).to_be_visible()
    page.reload()
    expect(
        page.get_by_role("region", name="Role Plan keeper").get_by_role(
            "checkbox", name=re.compile("^hours.view")
        )
    ).to_be_checked()

    page.get_by_role("region", name="Role Plan keeper").get_by_role(
        "button", name="Delete role"
    ).click()
    page.get_by_role("dialog").get_by_role("button", name="Delete role").click()
    expect(page.get_by_role("region", name="Role Plan keeper")).to_have_count(0)


def test_default_access_is_added_and_removed(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "access")
    signed_in = page.get_by_role("region", name="Everybody who is signed in")
    expect(signed_in).to_contain_text("Viewer · Everywhere")
    expect(signed_in).to_contain_text("Hours viewer · Own department")
    anybody = page.get_by_role("region", name="Anybody, signed in or not")
    expect(anybody).to_contain_text("Nothing.")

    signed_in.get_by_label("Role to grant Everybody who is signed in").select_option(
        label="Project administrator"
    )
    signed_in.get_by_label("Where to grant Everybody who is signed in").select_option(label="STL")
    signed_in.get_by_role("button", name="Add").click()
    expect(signed_in).to_contain_text("Project administrator · STL")
    signed_in.get_by_role(
        "button", name="Remove Project administrator (STL) from the defaults"
    ).click()
    expect(signed_in.locator(".admin-assignment")).to_have_count(2)
    expect(signed_in.locator(".admin-assignments")).not_to_contain_text("Project administrator")


# ---------------------------------------------------------------- audit log (ADM-6)


def test_the_audit_log_shows_changes_and_filters_by_kind(sample_server: str, page: Page) -> None:
    open_admin(page, sample_server, "org")
    org_row(page, "STL").get_by_role("button", name="+ Branch").click()
    page.get_by_label("New branch under STL").fill("Metrology")
    page.get_by_role("button", name="Add", exact=True).click()
    expect(org_row(page, "Metrology")).to_be_visible()

    page.get_by_role("link", name="Audit log").click()
    first = page.locator(".admin-table tbody tr").first
    expect(first).to_contain_text("Branch added")
    expect(first).to_contain_text("Administrator")
    page.locator(".admin-toolbar select").select_option(label="Sign-ins")
    expect(page.locator(".admin-table tbody tr").first).to_contain_text("Signed in")
    expect(page.locator(".admin-table tbody tr", has_text="Branch added")).to_have_count(0)


# ---------------------------------------------------------------- the profile (ADM-8)


def test_the_profile_shows_own_data_and_changes_the_password(
    browser: Browser, sample_server: str, page: Page
) -> None:
    remember(page)
    page.goto(f"{sample_server}profile")
    sign_in(page, "anna.claes")
    expect(page.get_by_role("heading", level=1)).to_have_text("Anna Claes")
    about = page.get_by_role("region", name="About you")
    expect(about).to_contain_text("STL › Quality")
    expect(about).to_contain_text("40 h a week")
    expect(about).to_contain_text("anna.claes")
    expect(page.get_by_role("region", name="Availability")).to_contain_text("245 d")

    form = page.get_by_role("region", name="Change password")
    form.get_by_label("Current password").fill("not-my-password")
    form.get_by_label("New password (at least 10 characters)").fill("a-brand-new-secret")
    form.get_by_label("New password again").fill("a-brand-new-secret")
    form.get_by_role("button", name="Change password").click()
    expect(form.get_by_role("alert")).to_be_visible()

    form.get_by_label("Current password").fill(DEMO_PASSWORD)
    form.get_by_role("button", name="Change password").click()
    expect(toast(page, "Password changed")).to_be_visible()

    context = browser.new_context()
    try:
        other = context.new_page()
        remember(other)
        other.goto(f"{sample_server}projects")
        dialog = other.get_by_role("dialog", name="Log in")
        dialog.get_by_label("Username").fill("anna.claes")
        dialog.get_by_label("Password").fill("a-brand-new-secret")
        dialog.get_by_role("button", name="Log in").click()
        dialog.wait_for(state="detached")
    finally:
        context.close()


def test_the_built_in_administrator_has_a_profile_without_an_org_place(
    sample_server: str, page: Page
) -> None:
    remember(page)
    page.goto(f"{sample_server}profile")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.get_by_role("heading", level=1)).to_have_text("Administrator")
    expect(page.get_by_role("region", name="About you")).to_contain_text("Department")
