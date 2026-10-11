"""Roles, default grants and the audit log (users.manage); the profile page's own record.

Every endpoint with its 401 / 403 / 404 / 409 / 422 cases. [ADM-5] [ADM-6] [ADM-8] [AUTH-4] [AUTH-5]
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update

from momato.db.models import User
from momato.db.models.people import UserStatus
from momato.db.session import Database
from momato.domain.access import Permission
from tests.api.conftest import ClientFactory
from tests.api.test_admin_people import holder
from tests.api.test_projects import node_id, person_id

AUDIT_FILTERED = {"limit": 200}


def role_by_key(client: TestClient, key: str) -> dict[str, Any]:
    return next(r for r in client.get("/api/admin/roles").json() if r["key"] == key)


# ---------------------------------------------------------------- who may


def test_a_visitor_gets_401_and_a_plain_person_403(clients: ClientFactory) -> None:
    visitor, anna = clients(), clients("anna.claes")
    requests: list[tuple[str, str, Any]] = [
        ("get", "/api/admin/permissions", None),
        ("get", "/api/admin/roles", None),
        ("post", "/api/admin/roles", {"key": "x1", "name": "X"}),
        ("patch", "/api/admin/roles/1", {"name": "X"}),
        ("delete", "/api/admin/roles/1", None),
        ("get", "/api/admin/default-grants", None),
        (
            "post",
            "/api/admin/default-grants",
            {"audience": "signed_in", "role_key": "viewer", "scope_kind": "global"},
        ),
        ("delete", "/api/admin/default-grants/1", None),
        ("get", "/api/admin/audit", None),
        ("get", "/api/account", None),
    ]
    for method, url, body in requests:
        kwargs = {"json": body} if body is not None else {}
        assert getattr(visitor, method)(url, **kwargs).status_code == 401, (method, url)
        if url != "/api/account":  # everybody signed in has an account page
            assert getattr(anna, method)(url, **kwargs).status_code == 403, (method, url)


def test_org_manage_alone_does_not_open_roles_or_the_log(
    clients: ClientFactory, sample_database: Database
) -> None:
    org = holder(clients, sample_database, "anna.claes", "org_only", Permission.ORG_MANAGE)
    assert org.get("/api/admin/roles").status_code == 403
    assert org.get("/api/admin/audit").status_code == 403
    assert org.get("/api/admin/default-grants").status_code == 403


# ---------------------------------------------------------------- roles


def test_the_catalog_and_the_built_in_roles_are_listed(admin: TestClient) -> None:
    catalog = admin.get("/api/admin/permissions").json()
    assert [p["value"] for p in catalog] == [p.value for p in Permission]
    scoped = {p["value"]: p["scoped"] for p in catalog}
    assert scoped["project.edit"] is True
    assert scoped["org.manage"] is False
    assert all(p["description"] for p in catalog)

    roles = admin.get("/api/admin/roles").json()
    assert {r["key"] for r in roles if r["is_builtin"]} == {
        "admin",
        "hours_viewer",
        "project_admin",
        "viewer",
    }
    viewer = role_by_key(admin, "viewer")
    assert viewer["is_builtin"] is True
    assert viewer["permissions"] == ["project.view"]
    assert viewer["default_grant_count"] == 1  # signed-in people (D-013)
    assert role_by_key(admin, "admin")["permissions"] == sorted(p.value for p in Permission)


def test_a_custom_role_is_created_edited_and_deleted(admin: TestClient) -> None:
    created = admin.post(
        "/api/admin/roles",
        json={
            "key": "plan_keeper",
            "name": "  Plan keeper ",
            "description": "Looks after plans",
            "permissions": ["project.view", "plan.manage", "plan.manage"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["is_builtin"], body["assignment_count"]) == ("Plan keeper", False, 0)
    assert body["permissions"] == ["plan.manage", "project.view"]

    updated = admin.patch(
        f"/api/admin/roles/{body['id']}",
        json={"name": "Plan keepers", "permissions": ["project.view"]},
    ).json()
    assert (updated["name"], updated["permissions"]) == ("Plan keepers", ["project.view"])

    deleted = admin.delete(f"/api/admin/roles/{body['id']}")
    assert deleted.status_code == 204
    assert all(r["key"] != "plan_keeper" for r in admin.get("/api/admin/roles").json())
    actions = [e["action"] for e in admin.get("/api/admin/audit", params={"limit": 3}).json()]
    assert actions == ["role.deleted", "role.updated", "role.created"]


def test_role_input_is_validated_and_built_ins_are_read_only(admin: TestClient) -> None:
    ok = {"key": "custom_one", "name": "Custom one", "permissions": []}
    assert admin.post("/api/admin/roles", json=ok).status_code == 201
    assert admin.post("/api/admin/roles", json=ok).status_code == 409
    for bad in (
        {**ok, "key": "Bad Key"},
        {**ok, "key": "x"},
        {**ok, "name": ""},
        {**ok, "name": "   "},
        {**ok, "key": "another", "permissions": ["not.a.permission"]},
    ):
        assert admin.post("/api/admin/roles", json=bad).status_code == 422, bad
    viewer = role_by_key(admin, "viewer")["id"]
    assert admin.patch(f"/api/admin/roles/{viewer}", json={"name": "Seer"}).status_code == 422
    assert admin.delete(f"/api/admin/roles/{viewer}").status_code == 422
    assert admin.patch("/api/admin/roles/999999", json={"name": "X"}).status_code == 404
    assert admin.delete("/api/admin/roles/999999").status_code == 404


def test_a_role_in_use_is_not_deleted(admin: TestClient) -> None:
    role = admin.post(
        "/api/admin/roles",
        json={"key": "in_use", "name": "In use", "permissions": ["project.view"]},
    ).json()
    bram = person_id(admin, "Bram Peeters")
    admin.post(
        f"/api/admin/people/{bram}/assignments", json={"role_key": "in_use", "scope_kind": "global"}
    )
    assert role_by_key(admin, "in_use")["assignment_count"] == 1
    refused = admin.delete(f"/api/admin/roles/{role['id']}")
    assert refused.status_code == 409
    admin.post(
        "/api/admin/default-grants",
        json={"audience": "anonymous", "role_key": "in_use", "scope_kind": "global"},
    )
    assert role_by_key(admin, "in_use")["default_grant_count"] == 1


def test_a_role_edit_cannot_remove_the_last_administrator(
    clients: ClientFactory, sample_database: Database
) -> None:
    """[AUTH-4] Dropping users.manage from the only role that holds it would lock everyone out."""
    users = holder(clients, sample_database, "anna.claes", "users_only", Permission.USERS_MANAGE)
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "admin").values(status=UserStatus.SUSPENDED)
        )
    role = role_by_key(users, "users_only")
    refused = users.patch(f"/api/admin/roles/{role['id']}", json={"permissions": ["project.view"]})
    assert refused.status_code == 422
    assert role_by_key(users, "users_only")["permissions"] == ["users.manage"]


# ---------------------------------------------------------------- default grants


def test_the_default_grants_are_listed_with_their_scope_words(admin: TestClient) -> None:
    grants = admin.get("/api/admin/default-grants").json()
    pairs = {(g["audience"], g["role_key"], g["scope_kind"], g["scope_label"]) for g in grants}
    assert pairs == {
        ("signed_in", "viewer", "global", "Everywhere"),
        ("signed_in", "hours_viewer", "own_department", "Own department"),
    }


def test_a_default_grant_is_added_and_removed_and_changes_what_people_hold(
    clients: ClientFactory, admin: TestClient
) -> None:
    """[ADM-5] [D-013] Everybody signed in becomes a project administrator of STL."""
    anna = clients("anna.claes")
    stl = node_id(admin, "STL")
    before = anna.get("/api/auth/me").json()["permissions"]["project.edit"]
    assert before == {"everywhere": False, "node_ids": []}

    added = admin.post(
        "/api/admin/default-grants",
        json={
            "audience": "signed_in",
            "role_key": "project_admin",
            "scope_kind": "node",
            "node_id": stl,
        },
    )
    assert added.status_code == 201
    new = next(g for g in added.json() if g["role_key"] == "project_admin")
    assert new["scope_label"] == "STL"
    assert anna.get("/api/auth/me").json()["permissions"]["project.edit"]["node_ids"] == [stl]

    duplicate = admin.post(
        "/api/admin/default-grants",
        json={
            "audience": "signed_in",
            "role_key": "project_admin",
            "scope_kind": "node",
            "node_id": stl,
        },
    )
    assert duplicate.status_code == 409

    remaining = admin.delete(f"/api/admin/default-grants/{new['id']}")
    assert remaining.status_code == 200
    assert all(g["role_key"] != "project_admin" for g in remaining.json())
    assert anna.get("/api/auth/me").json()["permissions"]["project.edit"]["node_ids"] == []
    actions = [e["action"] for e in admin.get("/api/admin/audit", params={"limit": 2}).json()]
    assert actions == ["access.default_revoked", "access.default_granted"]


def test_default_grants_are_validated(admin: TestClient) -> None:
    body = {"audience": "signed_in", "role_key": "viewer", "scope_kind": "global"}
    assert admin.post("/api/admin/default-grants", json=body).status_code == 409  # exists already
    assert (
        admin.post("/api/admin/default-grants", json={**body, "role_key": "nope"}).status_code
        == 404
    )
    assert (
        admin.post("/api/admin/default-grants", json={**body, "audience": "nobody"}).status_code
        == 422
    )
    assert (
        admin.post("/api/admin/default-grants", json={**body, "scope_kind": "node"}).status_code
        == 422
    )
    far = {**body, "scope_kind": "node", "node_id": 999_999}
    assert admin.post("/api/admin/default-grants", json=far).status_code == 422
    assert admin.delete("/api/admin/default-grants/999999").status_code == 404


# ---------------------------------------------------------------- audit log


def test_the_audit_log_is_newest_first_and_pages_back(admin: TestClient) -> None:
    for name in ("One", "Two", "Three"):
        admin.post("/api/admin/roles", json={"key": f"role_{name.lower()}", "name": name})
    first = admin.get("/api/admin/audit", params={"limit": 2}).json()
    assert [e["details"]["name"] for e in first] == ["Three", "Two"]
    assert all(e["actor"] == "Administrator" for e in first)
    older = admin.get("/api/admin/audit", params={"limit": 2, "before_id": first[-1]["id"]}).json()
    assert older[0]["details"]["name"] == "One"
    assert older[0]["id"] < first[-1]["id"]
    ids = [e["id"] for e in admin.get("/api/admin/audit", params=AUDIT_FILTERED).json()]
    assert ids == sorted(ids, reverse=True)


def test_the_audit_log_can_be_filtered_by_kind_and_actor(
    clients: ClientFactory, admin: TestClient
) -> None:
    clients("anna.claes")  # a sign-in is an audit entry too
    admin.post("/api/admin/roles", json={"key": "filtered", "name": "Filtered"})
    everything = admin.get("/api/admin/audit", params=AUDIT_FILTERED).json()
    roles = admin.get("/api/admin/audit", params={**AUDIT_FILTERED, "action": "role."}).json()
    assert roles and all(e["action"].startswith("role.") for e in roles)
    assert len(roles) < len(everything)
    logins = admin.get("/api/admin/audit", params={**AUDIT_FILTERED, "action": "auth."}).json()
    assert {e["action"] for e in logins} == {"auth.login"}
    anna = person_id(admin, "Anna Claes")
    by_anna = admin.get("/api/admin/audit", params={**AUDIT_FILTERED, "actor_id": anna}).json()
    assert by_anna and all(e["actor_id"] == anna for e in by_anna)
    # a `%` or `_` in the filter is literal
    assert admin.get("/api/admin/audit", params={"action": "%"}).json() == []


def test_audit_paging_input_is_validated(admin: TestClient) -> None:
    assert admin.get("/api/admin/audit", params={"limit": 0}).status_code == 422
    assert admin.get("/api/admin/audit", params={"limit": 201}).status_code == 422
    assert admin.get("/api/admin/audit", params={"before_id": "x"}).status_code == 422


# ---------------------------------------------------------------- the profile page (ADM-8)


def test_a_person_sees_their_own_record_and_availability(clients: ClientFactory) -> None:
    anna = clients("anna.claes").get("/api/account")
    assert anna.status_code == 200
    body = anna.json()
    assert body["name"] == "Anna Claes"
    assert body["org_path"] == ["STL", "Quality"]
    assert body["department"] == "STL"
    assert body["username"] == "anna.claes"
    assert body["work_minutes"] == [480, 480, 480, 480, 480]
    assert body["password_sign_in"] is True
    assert [a["year"] for a in body["availability"]] == [2026, 2027]
    assert body["availability"][0]["days"] == 245  # her override in the sample (D-020)
    assert body["availability"][0]["override_days"] == 245


def test_the_built_in_administrator_has_a_profile_without_an_org_place(admin: TestClient) -> None:
    body = admin.get("/api/account").json()
    assert body["name"] == "Administrator"
    assert body["org_path"] == []
    assert body["department"] is None


def test_the_profile_follows_changes_by_administrators(
    clients: ClientFactory, admin: TestClient
) -> None:
    anna = clients("anna.claes")
    me = person_id(admin, "Anna Claes")
    admin.patch(f"/api/admin/people/{me}", json={"job_title": "Lead", "work_minutes": [420] * 5})
    admin.put(f"/api/admin/people/{me}/availability/2027", json={"days": 100})
    body = anna.get("/api/account").json()
    assert body["job_title"] == "Lead"
    assert body["work_minutes"] == [420] * 5
    year = next(a for a in body["availability"] if a["year"] == 2027)
    assert year["days"] == 100
    assert year["default_days"] == 220 * 35 / 40  # the profile's days × the capacity factor
