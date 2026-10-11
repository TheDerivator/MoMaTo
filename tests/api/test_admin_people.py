"""People administration: data, availability, deactivation (org.manage), sign-in and rights
(users.manage); every endpoint with its 401 / 403 / 404 / 409 / 422 cases.
[ADM-2] [ADM-3] [ADM-4] [ADM-5] [AUTH-4] [AUTH-5]
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from momato.db.models import ProjectMember, Role, RolePermission, TimeEntry, User
from momato.db.models.people import UserStatus
from momato.db.session import Database
from momato.domain.access import Permission, Scope
from tests.api.conftest import ClientFactory, grant
from tests.api.test_projects import bootstrap, node_id, person_id
from tests.conftest import DEMO_PASSWORD
from tests.helpers import count_statements, login


def make_role(database: Database, key: str, *permissions: Permission) -> None:
    """A custom role holding exactly `permissions`."""
    with database.session(write=True) as session:
        role = Role(key=key, name=key.replace("_", " ").title(), is_builtin=False)
        role.permissions = [RolePermission(permission=p.value) for p in permissions]
        session.add(role)


def holder(
    clients: ClientFactory, database: Database, username: str, role: str, *permissions: Permission
) -> TestClient:
    """`username` holding a custom role with `permissions` everywhere."""
    make_role(database, role, *permissions)
    grant(database, username, role, Scope.everywhere())
    return clients(username)


def person(client: TestClient, name: str) -> dict[str, Any]:
    response = client.get("/api/admin/people", params={"q": name})
    assert response.status_code == 200, response.text
    return next(p for p in response.json() if p["name"] == name)


# ---------------------------------------------------------------- who may


def test_a_visitor_gets_401_and_a_plain_person_403(clients: ClientFactory) -> None:
    visitor, anna = clients(), clients("anna.claes")
    someone = person_id(anna, "Bram Peeters")
    requests: list[tuple[str, str, Any]] = [
        ("get", "/api/admin/people", None),
        ("get", f"/api/admin/people/{someone}", None),
        ("post", "/api/admin/people", {"name": "X", "org_node_id": 1}),
        ("patch", f"/api/admin/people/{someone}", {"name": "Y"}),
        ("put", f"/api/admin/people/{someone}/availability/2026", {"days": 100}),
        ("delete", f"/api/admin/people/{someone}/availability/2026", None),
        ("post", f"/api/admin/people/{someone}/deactivate", None),
        ("post", f"/api/admin/people/{someone}/reactivate", None),
        ("patch", f"/api/admin/people/{someone}/sign-in", {"email": "x@example.org"}),
        ("post", f"/api/admin/people/{someone}/password", {}),
        ("put", f"/api/admin/people/{someone}/status", {"status": "suspended"}),
        (
            "post",
            f"/api/admin/people/{someone}/assignments",
            {"role_key": "viewer", "scope_kind": "global"},
        ),
        ("delete", f"/api/admin/people/{someone}/assignments/1", None),
    ]
    for method, url, body in requests:
        kwargs = {"json": body} if body is not None else {}
        assert getattr(visitor, method)(url, **kwargs).status_code == 401, (method, url)
        assert getattr(anna, method)(url, **kwargs).status_code == 403, (method, url)


def test_each_right_opens_its_own_half(clients: ClientFactory, sample_database: Database) -> None:
    org = holder(clients, sample_database, "anna.claes", "org_only", Permission.ORG_MANAGE)
    users = holder(clients, sample_database, "bram.peeters", "users_only", Permission.USERS_MANAGE)
    bram = person_id(org, "Bram Peeters")
    # org.manage edits the person's data, not their sign-in or rights
    assert org.patch(f"/api/admin/people/{bram}", json={"hue": 10}).status_code == 200
    assert (
        org.patch(f"/api/admin/people/{bram}/sign-in", json={"email": "b@x.org"}).status_code == 403
    )
    assert org.post(f"/api/admin/people/{bram}/password", json={}).status_code == 403
    assert (
        org.put(f"/api/admin/people/{bram}/status", json={"status": "suspended"}).status_code == 403
    )
    # users.manage the other way round
    anna = person_id(users, "Anna Claes")
    assert users.patch(f"/api/admin/people/{anna}", json={"hue": 10}).status_code == 403
    assert (
        users.put(f"/api/admin/people/{anna}/availability/2026", json={"days": 9}).status_code
        == 403
    )
    assert users.post(f"/api/admin/people/{anna}/deactivate").status_code == 403
    assert (
        users.patch(f"/api/admin/people/{anna}/sign-in", json={"email": "a@x.org"}).status_code
        == 200
    )


def test_sign_in_and_rights_are_only_shown_to_users_managers(
    clients: ClientFactory, sample_database: Database, admin: TestClient
) -> None:
    org = holder(clients, sample_database, "anna.claes", "org_only", Permission.ORG_MANAGE)
    seen_by_org = person(org, "Bram Peeters")
    assert seen_by_org["username"] is None
    assert seen_by_org["email"] is None
    assert seen_by_org["has_password"] is False
    assert seen_by_org["assignments"] == []
    seen_by_admin = person(admin, "Bram Peeters")
    assert seen_by_admin["username"] == "bram.peeters"
    assert seen_by_admin["has_password"] is True
    # the search by username only works for those who may see usernames
    assert org.get("/api/admin/people", params={"q": "bram.peeters"}).json() == []
    assert [
        p["name"] for p in admin.get("/api/admin/people", params={"q": "bram.peeters"}).json()
    ] == ["Bram Peeters"]


def test_the_list_holds_everyone_and_filters_by_name(admin: TestClient) -> None:
    everyone = admin.get("/api/admin/people").json()
    assert len(everyone) == len(bootstrap(admin)["people"])
    assert [p["name"] for p in everyone] == sorted(p["name"] for p in everyone)
    found = admin.get("/api/admin/people", params={"q": "claes"}).json()
    assert [p["name"] for p in found] == ["Anna Claes"]
    assert admin.get("/api/admin/people/999999").status_code == 404
    # system accounts are not people
    assert not any(p["name"] in {"Administrator", "Anonymous"} for p in everyone)


# ---------------------------------------------------------------- create and edit (org.manage)


def test_a_person_is_created_without_a_sign_in_and_appears_in_the_pickers(
    admin: TestClient,
) -> None:
    quality = node_id(admin, "Quality")
    response = admin.post(
        "/api/admin/people",
        json={
            "name": "  Nora Vandamme ",
            "job_title": "Quality engineer",
            "org_node_id": quality,
            "hue": 40,
            "work_minutes": [480, 480, 480, 480, 240],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["name"], body["job_title"], body["hue"], body["status"]) == (
        "Nora Vandamme",
        "Quality engineer",
        40,
        "active",
    )
    assert body["work_minutes"] == [480, 480, 480, 480, 240]
    assert body["username"] is None
    assert body["has_password"] is False
    assert any(p["name"] == "Nora Vandamme" and p["active"] for p in bootstrap(admin)["people"])
    hits = admin.get("/api/search/people", params={"q": "Nora"}).json()
    assert [h["name"] for h in hits] == ["Nora Vandamme"]
    assert (
        admin.get("/api/admin/audit", params={"limit": 1}).json()[0]["action"] == "person.created"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "org_node_id": 1},
        {"name": "No node"},
        {"name": "Far node", "org_node_id": 999_999},
        {"name": "Short week", "org_node_id": 1, "work_minutes": [480, 480]},
        {"name": "Negative", "org_node_id": 1, "work_minutes": [480, 480, 480, 480, -1]},
        {"name": "Too long", "org_node_id": 1, "work_minutes": [480, 480, 480, 480, 721]},
        {"name": "Bad hue", "org_node_id": 1, "hue": 360},
    ],
)
def test_a_new_person_is_validated(admin: TestClient, body: dict[str, Any]) -> None:
    if body.get("org_node_id") == 1:
        body = {**body, "org_node_id": node_id(admin, "Quality")}
    assert admin.post("/api/admin/people", json=body).status_code == 422


def test_a_person_is_edited_field_by_field(admin: TestClient) -> None:
    anna = person_id(admin, "Anna Claes")
    process = node_id(admin, "Process")
    body = admin.patch(
        f"/api/admin/people/{anna}",
        json={"name": "Anna Claes-Smit", "job_title": "Senior engineer", "org_node_id": process},
    ).json()
    assert (body["name"], body["job_title"], body["org_node_id"]) == (
        "Anna Claes-Smit",
        "Senior engineer",
        process,
    )
    assert (
        admin.patch(f"/api/admin/people/{anna}", json={"job_title": None}).json()["job_title"]
        is None
    )
    # unsent fields stay
    assert (
        admin.patch(f"/api/admin/people/{anna}", json={"hue": 90}).json()["name"]
        == "Anna Claes-Smit"
    )
    entry = admin.get("/api/admin/audit", params={"limit": 1}).json()[0]
    assert entry["action"] == "person.updated"
    assert entry["details"]["hue"] == 90
    assert (
        admin.patch(f"/api/admin/people/{anna}", json={"org_node_id": 999_999}).status_code == 422
    )
    assert admin.patch("/api/admin/people/999999", json={"name": "Z"}).status_code == 404
    # system accounts are not reachable as people
    admin_id = admin.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/admin/people/{admin_id}", json={"name": "Z"}).status_code == 404


def test_a_work_pattern_changes_the_timesheet_target(
    clients: ClientFactory, admin: TestClient
) -> None:
    """[ADM-2] [D-019] Anna works four days: Friday has no target any more."""
    anna_client = clients("anna.claes")
    before = [d["target_minutes"] for d in anna_client.get("/api/timesheet").json()["days"]]
    assert before == [480, 480, 480, 480, 480]
    anna = person_id(admin, "Anna Claes")
    pattern = [480, 480, 480, 480, 0]
    assert (
        admin.patch(f"/api/admin/people/{anna}", json={"work_minutes": pattern}).status_code == 200
    )
    after = [d["target_minutes"] for d in anna_client.get("/api/timesheet").json()["days"]]
    assert after == pattern
    # and the bootstrap carries the new pattern for the planning screens
    assert next(p for p in bootstrap(admin)["people"] if p["id"] == anna)["work_minutes"] == pattern


# ---------------------------------------------------------------- availability


def test_an_availability_override_replaces_the_default_and_shows_in_planning(
    admin: TestClient,
) -> None:
    """[ADM-4] [D-020]"""
    everyone = admin.get("/api/admin/people").json()
    # someone the sample gave no override: this year and next come from the default
    chosen = next(
        p
        for p in everyone
        if next(a for a in p["availability"] if a["year"] == 2026)["override_days"] is None
    )
    anna, name = chosen["id"], chosen["name"]
    years = {a["year"]: a for a in chosen["availability"]}
    assert set(years) == {2026, 2027}
    default = years[2026]["default_days"]
    assert years[2026]["days"] == default

    body = admin.put(f"/api/admin/people/{anna}/availability/2026", json={"days": "180.5"}).json()
    year = next(a for a in body["availability"] if a["year"] == 2026)
    assert (year["override_days"], year["days"], year["default_days"]) == (180.5, 180.5, default)

    plan = admin.get("/api/people-planning", params={"q": name}).json()
    total = plan["rows"][0]["total"]
    assert total["free"] == pytest.approx(180.5 - total["value"], abs=0.01)

    cleared = admin.delete(f"/api/admin/people/{anna}/availability/2026").json()
    year = next(a for a in cleared["availability"] if a["year"] == 2026)
    assert (year["override_days"], year["days"]) == (None, default)
    plan = admin.get("/api/people-planning", params={"q": name}).json()
    total = plan["rows"][0]["total"]
    assert total["free"] == pytest.approx(default - total["value"], abs=0.01)


def test_an_override_for_a_far_year_is_listed_and_the_numbers_are_checked(
    admin: TestClient,
) -> None:
    anna = person_id(admin, "Anna Claes")
    body = admin.put(f"/api/admin/people/{anna}/availability/2029", json={"days": 100}).json()
    assert 2029 in [a["year"] for a in body["availability"]]
    assert (
        admin.put(f"/api/admin/people/{anna}/availability/2026", json={"days": -1}).status_code
        == 422
    )
    assert (
        admin.put(f"/api/admin/people/{anna}/availability/2026", json={"days": 367}).status_code
        == 422
    )
    assert (
        admin.put(f"/api/admin/people/{anna}/availability/1999", json={"days": 10}).status_code
        == 422
    )
    assert (
        admin.put("/api/admin/people/999999/availability/2026", json={"days": 10}).status_code
        == 404
    )
    assert (
        admin.delete(f"/api/admin/people/{anna}/availability/2031").status_code == 200
    )  # nothing to clear


# ---------------------------------------------------------------- deactivate and reactivate


def test_a_deactivated_person_leaves_pickers_and_planning_but_keeps_their_history(
    clients: ClientFactory, admin: TestClient, sample_database: Database
) -> None:
    """[ADM-2] [AUTH-4]"""
    bram_client = clients("bram.peeters")
    bram = person_id(admin, "Bram Peeters")
    with sample_database.session() as session:
        members = session.scalar(
            select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == bram)
        )
        entries = session.scalar(
            select(func.count()).select_from(TimeEntry).where(TimeEntry.user_id == bram)
        )
    assert members and entries
    assert bram_client.get("/api/bootstrap").status_code == 200

    response = admin.post(f"/api/admin/people/{bram}/deactivate")
    assert response.status_code == 200
    assert response.json()["status"] == "deactivated"

    # the open session ended, and signing in again is refused
    assert bram_client.get("/api/bootstrap").status_code == 401
    assert login(clients(), "bram.peeters", DEMO_PASSWORD).status_code == 401
    # out of pickers and planning rows
    assert next(p for p in bootstrap(admin)["people"] if p["id"] == bram)["active"] is False
    assert admin.get("/api/search/people", params={"q": "Bram"}).json() == []
    rows = admin.get("/api/people-planning", params={"q": "Bram"}).json()["rows"]
    assert rows == []
    # ... and cannot be chosen again as a coordinator
    created = admin.post(
        "/api/projects",
        json={
            "name": "Needs a coordinator",
            "org_node_id": node_id(admin, "Quality"),
            "coordinator_id": bram,
            "start_date": "2026-11-01",
            "end_date": "2026-12-01",
        },
    )
    assert created.status_code == 422
    # history is untouched
    with sample_database.session() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == bram)
            )
            == members
        )
        assert (
            session.scalar(
                select(func.count()).select_from(TimeEntry).where(TimeEntry.user_id == bram)
            )
            == entries
        )
    # listed for administrators, with the status
    assert person(admin, "Bram Peeters")["status"] == "deactivated"

    again = admin.post(f"/api/admin/people/{bram}/reactivate")
    assert again.json()["status"] == "active"
    assert login(clients(), "bram.peeters", DEMO_PASSWORD).status_code == 200
    assert next(p for p in bootstrap(admin)["people"] if p["id"] == bram)["active"] is True


def test_deactivating_twice_or_reactivating_an_active_person_is_a_conflict(
    admin: TestClient,
) -> None:
    bram = person_id(admin, "Bram Peeters")
    assert admin.post(f"/api/admin/people/{bram}/reactivate").status_code == 409
    assert admin.post(f"/api/admin/people/{bram}/deactivate").status_code == 200
    assert admin.post(f"/api/admin/people/{bram}/deactivate").status_code == 409
    assert admin.post("/api/admin/people/999999/deactivate").status_code == 404


def test_nobody_deactivates_themselves_or_the_last_administrator(
    clients: ClientFactory, sample_database: Database
) -> None:
    """[AUTH-4] At least one active administrator always remains."""
    org = holder(clients, sample_database, "anna.claes", "org_only", Permission.ORG_MANAGE)
    anna = person_id(org, "Anna Claes")
    myself = org.post(f"/api/admin/people/{anna}/deactivate")
    assert myself.status_code == 422
    assert "your own account" in myself.json()["message"]

    # Bram becomes the only active administrator: the built-in admin account is out
    grant(sample_database, "bram.peeters", "admin", Scope.everywhere())
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "admin").values(status=UserStatus.SUSPENDED)
        )
    bram = person_id(org, "Bram Peeters")
    refused = org.post(f"/api/admin/people/{bram}/deactivate")
    assert refused.status_code == 422
    assert "nobody able to manage users" in refused.json()["message"]
    assert person(org, "Bram Peeters")["status"] == "active"


# ---------------------------------------------------------------- sign-in (users.manage)


def test_a_username_is_set_checked_and_cleared(admin: TestClient, clients: ClientFactory) -> None:
    bram = person_id(admin, "Bram Peeters")
    body = admin.patch(
        f"/api/admin/people/{bram}/sign-in",
        json={"username": " Bram.NEW ", "email": "Bram@Example.org"},
    ).json()
    assert (body["username"], body["email"]) == ("bram.new", "bram@example.org")
    assert login(clients(), "bram.new", DEMO_PASSWORD).status_code == 200

    taken = admin.patch(f"/api/admin/people/{bram}/sign-in", json={"username": "anna.claes"})
    assert taken.status_code == 409
    bad = admin.patch(f"/api/admin/people/{bram}/sign-in", json={"username": "bad name!"})
    assert bad.status_code == 422
    same_email = admin.patch(
        f"/api/admin/people/{person_id(admin, 'Anna Claes')}/sign-in",
        json={"email": "bram@example.org"},
    )
    assert same_email.status_code == 409

    cleared = admin.patch(f"/api/admin/people/{bram}/sign-in", json={"username": None}).json()
    assert cleared["username"] is None
    assert cleared["has_password"] is False  # no name, no password sign-in
    assert login(clients(), "bram.new", DEMO_PASSWORD).status_code == 401
    assert (
        admin.get("/api/admin/audit", params={"limit": 1}).json()[0]["action"]
        == "user.sign_in_changed"
    )


def test_a_password_is_generated_once_and_must_be_changed_at_first_sign_in(
    clients: ClientFactory, admin: TestClient
) -> None:
    bram_client = clients("bram.peeters")
    bram = person_id(admin, "Bram Peeters")
    body = admin.post(f"/api/admin/people/{bram}/password", json={}).json()
    password = body["generated_password"]
    assert password
    assert bram_client.get("/api/bootstrap").status_code == 401  # their sessions ended

    new_client = clients()
    response = login(new_client, "bram.peeters", password)
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
    assert new_client.get("/api/bootstrap").status_code == 403  # nothing else until they change it
    assert login(clients(), "bram.peeters", DEMO_PASSWORD).status_code == 401
    # the password is never part of what the administration lists
    assert password not in admin.get(f"/api/admin/people/{bram}").text
    entry = admin.get("/api/admin/audit", params={"limit": 1, "action": "user."}).json()[0]
    assert entry["action"] == "user.password_reset"
    assert password not in str(entry)


def test_a_chosen_password_follows_the_policy_and_needs_a_username(
    admin: TestClient, clients: ClientFactory
) -> None:
    bram = person_id(admin, "Bram Peeters")
    weak = admin.post(f"/api/admin/people/{bram}/password", json={"password": "short"})
    assert weak.status_code == 422
    chosen = admin.post(
        f"/api/admin/people/{bram}/password", json={"password": "a-long-enough-secret"}
    )
    assert chosen.status_code == 200
    assert chosen.json()["generated_password"] is None
    assert login(clients(), "bram.peeters", "a-long-enough-secret").status_code == 200

    nora = admin.post(
        "/api/admin/people",
        json={"name": "Nora Vandamme", "org_node_id": node_id(admin, "Quality")},
    ).json()
    refused = admin.post(f"/api/admin/people/{nora['id']}/password", json={})
    assert refused.status_code == 422
    assert "username" in refused.json()["message"]
    # username first, then the password: a new person can sign in
    admin.patch(f"/api/admin/people/{nora['id']}/sign-in", json={"username": "nora.vandamme"})
    given = admin.post(f"/api/admin/people/{nora['id']}/password", json={}).json()
    assert login(clients(), "nora.vandamme", given["generated_password"]).status_code == 200


def test_suspending_ends_sessions_and_reactivating_restores_the_sign_in(
    clients: ClientFactory, admin: TestClient
) -> None:
    """[ADM-3] [AUTH-4] A suspended person still works here: they stay in planning."""
    bram_client = clients("bram.peeters")
    bram = person_id(admin, "Bram Peeters")
    body = admin.put(f"/api/admin/people/{bram}/status", json={"status": "suspended"}).json()
    assert body["status"] == "suspended"
    assert bram_client.get("/api/bootstrap").status_code == 401
    assert login(clients(), "bram.peeters", DEMO_PASSWORD).status_code == 401
    assert admin.get("/api/people-planning", params={"q": "Bram"}).json()["rows"]  # still planned
    assert next(p for p in bootstrap(admin)["people"] if p["id"] == bram)["active"] is True
    assert (
        admin.put(f"/api/admin/people/{bram}/status", json={"status": "active"}).status_code == 200
    )
    assert login(clients(), "bram.peeters", DEMO_PASSWORD).status_code == 200
    # leaving the company is a separate action
    refused = admin.put(f"/api/admin/people/{bram}/status", json={"status": "deactivated"})
    assert refused.status_code == 422


# ---------------------------------------------------------------- assignments (users.manage)


def test_a_role_is_assigned_at_a_scope_and_taken_away(admin: TestClient) -> None:
    bram = person_id(admin, "Bram Peeters")
    stl = node_id(admin, "STL")
    body = admin.post(
        f"/api/admin/people/{bram}/assignments",
        json={"role_key": "project_admin", "scope_kind": "node", "node_id": stl},
    )
    assert body.status_code == 201
    assignment = body.json()["assignments"][0]
    assert (assignment["role_key"], assignment["scope_kind"], assignment["scope_label"]) == (
        "project_admin",
        "node",
        "STL",
    )
    own = admin.post(
        f"/api/admin/people/{bram}/assignments",
        json={"role_key": "hours_viewer", "scope_kind": "own_department"},
    ).json()
    assert [a["scope_label"] for a in own["assignments"]] == ["STL", "Own department"]
    everywhere = admin.post(
        f"/api/admin/people/{bram}/assignments",
        json={"role_key": "viewer", "scope_kind": "global"},
    ).json()
    assert everywhere["assignments"][-1]["scope_label"] == "Everywhere"

    removed = admin.delete(f"/api/admin/people/{bram}/assignments/{assignment['id']}").json()
    assert [a["role_key"] for a in removed["assignments"]] == ["hours_viewer", "viewer"]
    actions = [e["action"] for e in admin.get("/api/admin/audit", params={"limit": 4}).json()]
    assert actions[0] == "user.role_revoked"
    assert actions[1:] == ["user.role_granted"] * 3


def test_assignments_are_validated(admin: TestClient) -> None:
    bram = person_id(admin, "Bram Peeters")
    url = f"/api/admin/people/{bram}/assignments"
    first = {"role_key": "project_admin", "scope_kind": "global"}
    assert admin.post(url, json=first).status_code == 201
    assert admin.post(url, json=first).status_code == 409  # already holds it there
    unknown = admin.post(url, json={"role_key": "nope", "scope_kind": "global"})
    assert unknown.status_code == 404
    no_node = admin.post(url, json={"role_key": "viewer", "scope_kind": "node"})
    assert no_node.status_code == 422
    stray_node = admin.post(
        url, json={"role_key": "viewer", "scope_kind": "global", "node_id": node_id(admin, "STL")}
    )
    assert stray_node.status_code == 422
    far = admin.post(url, json={"role_key": "viewer", "scope_kind": "node", "node_id": 999_999})
    assert far.status_code == 422
    # an assignment of somebody else is not this person's to remove
    others = admin.post(
        f"/api/admin/people/{person_id(admin, 'Anna Claes')}/assignments",
        json={"role_key": "viewer", "scope_kind": "global"},
    ).json()["assignments"][0]["id"]
    assert admin.delete(f"/api/admin/people/{bram}/assignments/{others}").status_code == 404
    assert admin.delete(f"/api/admin/people/{bram}/assignments/999999").status_code == 404


def test_the_last_administrator_cannot_lose_the_role(
    clients: ClientFactory, sample_database: Database
) -> None:
    """[AUTH-4] Through the assignment endpoint too."""
    users = holder(clients, sample_database, "anna.claes", "users_only", Permission.USERS_MANAGE)
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "admin").values(status=UserStatus.SUSPENDED)
        )
    me = users.get("/api/admin/people", params={"q": "Anna Claes"}).json()[0]
    only = next(a for a in me["assignments"] if a["role_key"] == "users_only")
    refused = users.delete(f"/api/admin/people/{me['id']}/assignments/{only['id']}")
    assert refused.status_code == 422
    assert "nobody able to manage users" in refused.json()["message"]


def test_the_people_list_costs_the_same_statements_for_one_person_and_for_everyone(
    admin: TestClient,
) -> None:
    """[D-028] Overrides and assignments are loaded in bulk, not per person."""
    with count_statements() as one:
        assert len(admin.get("/api/admin/people", params={"q": "Anna Claes"}).json()) == 1
    with count_statements() as everyone:
        assert len(admin.get("/api/admin/people").json()) > 50
    assert one.count == everyone.count
