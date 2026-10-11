"""Login, logout, me, password change, CSRF, throttling, suspension. [AUTH-1] [AUTH-4]"""

import re
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from momato.config import Settings
from momato.db.base import utcnow
from momato.db.models import AuditEntry, LoginAttempt, RoleAssignment, User, UserSession
from momato.db.models.people import UserStatus
from momato.db.session import Database
from momato.web import create_app
from momato.web.csrf import CSRF_COOKIE, CSRF_HEADER
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.factories import make_org, make_user
from tests.helpers import login

ADMIN = "admin"


@pytest.fixture
def anna(database: Database) -> User:
    """A person who can sign in with a password and holds no assignment."""
    with database.session(write=True) as session:
        user = make_user(
            session,
            "Anna Claes",
            make_org(session, "STL", department=True),
            username="anna.claes",
            password="anna-password-1",
        )
        session.expunge(user)
    return user


# ---------------------------------------------------------------- me


def test_the_anonymous_visitor_is_told_who_they_are_and_that_they_may_nothing(
    client: TestClient,
) -> None:
    me = client.get("/api/auth/me").json()
    assert me["is_anonymous"] is True
    assert me["username"] == "anonymous"
    assert me["person_id"] is None
    assert me["must_change_password"] is False
    assert all(not r["everywhere"] and r["node_ids"] == [] for r in me["permissions"].values())
    assert set(me["permissions"]) == {
        "project.view",
        "project.edit",
        "project.comment",
        "project.delete",
        "plan.manage",
        "hours.view",
        "org.manage",
        "users.manage",
    }
    assert me["login"] == {"password": True, "providers": [], "windows": None}


def test_a_person_signed_in_sees_the_defaults_in_me(client: TestClient, anna: User) -> None:
    assert login(client, "anna.claes", "anna-password-1").status_code == 200
    me = client.get("/api/auth/me").json()
    assert (me["is_anonymous"], me["name"]) == (False, "Anna Claes")
    assert me["person_id"] == anna.id
    assert me["org_node_id"] == anna.org_node_id
    assert me["department_id"] == anna.org_node_id  # her node is the flagged department
    assert me["permissions"]["project.view"]["everywhere"] is True
    assert me["permissions"]["hours.view"] == {"everywhere": False, "node_ids": [anna.org_node_id]}
    assert me["permissions"]["project.edit"] == {"everywhere": False, "node_ids": []}


# ---------------------------------------------------------------- login and logout


def test_the_admin_can_log_in_and_the_session_cookie_is_httponly(client: TestClient) -> None:
    response = login(client, ADMIN, TEST_ADMIN_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == ADMIN
    assert body["is_system"] is True
    assert body["person_id"] is None  # a system account is not a person
    assert body["permissions"]["users.manage"]["everywhere"] is True
    cookie = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith("momato_session=")
    )
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie  # plain http in the tests
    assert client.get("/api/auth/me").json()["username"] == ADMIN


def test_usernames_are_case_insensitive(client: TestClient, anna: User) -> None:
    assert login(client, "  Anna.Claes ", "anna-password-1").status_code == 200


def test_wrong_credentials_are_refused_without_saying_which_part_was_wrong(
    client: TestClient, anna: User
) -> None:
    wrong_password = login(client, "anna.claes", "not the password")
    unknown_user = login(client, "nobody", "whatever password")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["error"] == "invalid_credentials"
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_nobody_can_sign_in_as_the_anonymous_visitor_or_without_a_password(
    client: TestClient, anna: User, database: Database
) -> None:
    assert login(client, "anonymous", "").status_code in {401, 422}
    assert login(client, "anonymous", "any password").status_code == 401
    with database.session(write=True) as session:
        make_user(session, "No Password", None, username="nopassword")
    assert login(client, "nopassword", "any password").status_code == 401


def test_logout_ends_the_session_on_the_server(client: TestClient, anna: User) -> None:
    login(client, "anna.claes", "anna-password-1")
    cookie = client.cookies["momato_session"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    client.cookies.set("momato_session", cookie)  # replaying the old cookie gets nothing
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_the_cookie_is_secure_when_configured(settings: Settings, anna: User) -> None:
    app = create_app(settings.model_copy(update={"cookie_secure": True}))
    with TestClient(app, base_url="https://testserver") as client:  # secure cookies need https
        client.get("/api/health")
        client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
        response = login(client, "anna.claes", "anna-password-1")
        assert response.status_code == 200
        cookies = response.headers.get_list("set-cookie")
        session_cookie = next(c for c in cookies if c.startswith("momato_session="))
        assert "Secure" in session_cookie


def test_sessions_expire(client: TestClient, anna: User, database: Database) -> None:
    login(client, "anna.claes", "anna-password-1")
    with database.session(write=True) as session:
        session.execute(update(UserSession).values(expires_at=utcnow() - timedelta(minutes=1)))
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_logins_are_audited(client: TestClient, anna: User, database: Database) -> None:
    """[AUTH-5]"""
    login(client, "anna.claes", "anna-password-1")
    with database.session() as session:
        entries = [a for a in session.scalars(select(AuditEntry)) if a.action == "auth.login"]
    assert len(entries) == 1
    assert entries[0].actor_user_id == anna.id


# ---------------------------------------------------------------- throttling


def test_the_sixth_failed_login_gets_429_even_with_the_right_password(
    client: TestClient, anna: User
) -> None:
    for _ in range(5):
        assert login(client, "anna.claes", "wrong password!").status_code == 401
    refused = login(client, "anna.claes", "anna-password-1")  # correct, but throttled
    assert refused.status_code == 429
    assert refused.json()["error"] == "too_many_attempts"
    assert int(refused.headers["retry-after"]) == 15 * 60


def test_a_success_resets_the_count_for_that_account(client: TestClient, anna: User) -> None:
    for _ in range(4):
        login(client, "anna.claes", "wrong password!")
    assert login(client, "anna.claes", "anna-password-1").status_code == 200
    for _ in range(4):
        assert login(client, "anna.claes", "wrong password!").status_code == 401


def test_failures_expire_with_the_window(
    client: TestClient, anna: User, database: Database
) -> None:
    for _ in range(5):
        login(client, "anna.claes", "wrong password!")
    with database.session(write=True) as session:
        session.execute(update(LoginAttempt).values(at=utcnow() - timedelta(minutes=16)))
    assert login(client, "anna.claes", "anna-password-1").status_code == 200


def test_one_address_trying_many_accounts_is_throttled_too(settings: Settings, anna: User) -> None:
    app = create_app(settings.model_copy(update={"login_max_failures_per_ip": 3}))
    for client in start_client(app):
        for index in range(3):
            assert login(client, f"user{index}", "wrong password!").status_code == 401
        assert login(client, "anna.claes", "anna-password-1").status_code == 429
        break


# ---------------------------------------------------------------- suspension and status


def test_a_suspended_persons_session_is_refused_at_the_next_request(
    client: TestClient, anna: User, database: Database
) -> None:
    login(client, "anna.claes", "anna-password-1")
    assert client.get("/api/auth/me").json()["username"] == "anna.claes"
    with database.session(write=True) as session:
        session.execute(update(User).where(User.id == anna.id).values(status=UserStatus.SUSPENDED))
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    assert login(client, "anna.claes", "anna-password-1").status_code == 401


def test_a_deactivated_person_cannot_sign_in(
    client: TestClient, anna: User, database: Database
) -> None:
    with database.session(write=True) as session:
        session.execute(
            update(User).where(User.id == anna.id).values(status=UserStatus.DEACTIVATED)
        )
    assert login(client, "anna.claes", "anna-password-1").status_code == 401


# ---------------------------------------------------------------- password change


def test_a_generated_admin_password_must_be_changed_before_anything_else(
    settings: Settings, database: Database
) -> None:
    with database.session(write=True) as session:
        admin = session.scalar(select(User).where(User.username == ADMIN))
        assert admin is not None
        admin.must_change_password = True
    app = create_app(settings)
    for client in start_client(app):
        me = login(client, ADMIN, TEST_ADMIN_PASSWORD).json()
        assert me["must_change_password"] is True
        assert all(not r["everywhere"] for r in me["permissions"].values())  # no rights yet
        changed = client.post(
            "/api/auth/password",
            json={"current_password": TEST_ADMIN_PASSWORD, "new_password": "a-brand-new-password"},
        )
        assert changed.status_code == 204
        again = client.get("/api/auth/me").json()
        assert again["must_change_password"] is False
        assert again["permissions"]["users.manage"]["everywhere"] is True
        break


def test_changing_the_password_validates_and_ends_the_other_sessions(
    settings: Settings, anna: User
) -> None:
    app = create_app(settings)
    first = next(start_client(app))
    second = TestClient(app)
    with second:
        second.get("/api/health")
        second.headers[CSRF_HEADER] = second.cookies[CSRF_COOKIE]
        login(first, "anna.claes", "anna-password-1")
        login(second, "anna.claes", "anna-password-1")

        body = {"current_password": "anna-password-1", "new_password": "ok"}
        assert first.post("/api/auth/password", json=body).status_code == 422  # too short
        body["new_password"] = "anna-password-1"
        assert first.post("/api/auth/password", json=body).status_code == 422  # unchanged
        wrong = {"current_password": "nope nope nope", "new_password": "another-password-9"}
        assert first.post("/api/auth/password", json=wrong).status_code == 401

        ok = {"current_password": "anna-password-1", "new_password": "another-password-9"}
        assert first.post("/api/auth/password", json=ok).status_code == 204
        assert first.get("/api/auth/me").json()["username"] == "anna.claes"  # this one stays
        assert second.get("/api/auth/me").json()["is_anonymous"] is True  # the other is gone

        assert login(first, "anna.claes", "anna-password-1").status_code == 401
        assert login(first, "anna.claes", "another-password-9").status_code == 200


def test_the_anonymous_visitor_cannot_change_a_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/password",
        json={"current_password": "whatever-it-is", "new_password": "another-password-9"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------- CSRF


@pytest.fixture
def bare_client(settings: Settings) -> Iterator[TestClient]:
    """A client that does not send the CSRF header (a foreign page, a script)."""
    with TestClient(create_app(settings)) as client:
        yield client


def test_a_state_changing_request_without_the_csrf_header_gets_403(
    bare_client: TestClient, anna: User
) -> None:
    bare_client.get("/api/health")  # the cookie arrives
    assert CSRF_COOKIE in bare_client.cookies
    response = login(bare_client, "anna.claes", "anna-password-1")
    assert response.status_code == 403
    assert response.json()["error"] == "csrf_failed"


def test_a_wrong_csrf_header_is_refused_and_the_right_one_accepted(
    bare_client: TestClient, anna: User
) -> None:
    bare_client.get("/api/health")
    wrong = bare_client.post(
        "/api/auth/login",
        json={"username": "anna.claes", "password": "anna-password-1"},
        headers={CSRF_HEADER: "not-the-cookie"},
    )
    assert wrong.status_code == 403
    right = bare_client.post(
        "/api/auth/login",
        json={"username": "anna.claes", "password": "anna-password-1"},
        headers={CSRF_HEADER: bare_client.cookies[CSRF_COOKIE]},
    )
    assert right.status_code == 200


def test_reading_needs_no_csrf_header_and_every_response_sets_the_cookie_once(
    bare_client: TestClient,
) -> None:
    first = bare_client.get("/api/auth/me")
    assert first.status_code == 200
    assert any(c.startswith(f"{CSRF_COOKIE}=") for c in first.headers.get_list("set-cookie"))
    second = bare_client.get("/api/auth/me")  # the browser now sends the cookie back
    assert not any(c.startswith(f"{CSRF_COOKIE}=") for c in second.headers.get_list("set-cookie"))


def test_a_bearer_request_needs_no_csrf_header(bare_client: TestClient) -> None:
    """[TOK-2] Judged by its token alone; (the token itself arrives in M11)."""
    response = bare_client.post(
        "/api/auth/logout", headers={"Authorization": "Bearer mm_something"}
    )
    assert response.status_code != 403


# ---------------------------------------------------------------- the data endpoints


PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/agent-guide"),  # a guide for agents: it holds no data
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}


def test_anonymous_visitors_get_401_on_every_data_endpoint(client: TestClient) -> None:
    """Walks the OpenAPI document, so endpoints added later are covered without a new test.

    Reads must answer 401 outright. Writes are sent an empty body: validation may answer first
    (422), but never a success, a 403 or a server error. (Later milestones add an explicit
    valid-body table so writes are held to 401 too.)
    """
    paths = client.get("/api/openapi.json").json()["paths"]
    checked = 0
    for path, operations in paths.items():
        for method in operations:
            if (method.upper(), path) in PUBLIC:
                continue
            url = re.sub(r"\{[^}]+\}", "1", path)
            response = client.request(method.upper(), url, json={} if method != "get" else None)
            if method == "get":
                assert response.status_code == 401, (method, path, response.status_code)
            else:
                assert response.status_code in {401, 404, 405, 422}, (method, path)
            checked += 1
    assert checked >= 1  # at least the password endpoint


def test_the_admin_has_an_assignment_and_nobody_else_does(
    client: TestClient, anna: User, database: Database
) -> None:
    with database.session() as session:
        holders = {a.user_id for a in session.scalars(select(RoleAssignment))}
        admin_id = session.scalar(select(User.id).where(User.username == ADMIN))
    assert holders == {admin_id}


# ---------------------------------------------------------------- client addresses and cost


def test_the_client_address_comes_from_a_trusted_proxy_only(
    settings: Settings, anna: User, database: Database
) -> None:
    """The throttle counts the address the trusted proxy forwarded, not the proxy's own."""
    trusted = settings.model_copy(update={"trusted_proxies": "testclient"})
    for client in start_client(create_app(trusted)):
        client.post(
            "/api/auth/login",
            json={"username": "anna.claes", "password": "wrong password!"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
        break
    untrusted = settings.model_copy(update={"trusted_proxies": "10.0.0.1"})
    for client in start_client(create_app(untrusted)):
        client.post(
            "/api/auth/login",
            json={"username": "anna.claes", "password": "wrong password!"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        break
    with database.session() as session:
        addresses = sorted(
            a for a in session.scalars(select(LoginAttempt.ip_address)) if a is not None
        )
    assert addresses == ["203.0.113.9", "testclient"]  # the second header was not believed


def test_a_request_costs_a_fixed_number_of_statements(client: TestClient, anna: User) -> None:
    """Statement counts must not grow with the data (PLAN, test strategy 8)."""
    from tests.helpers import count_statements

    with count_statements() as anonymous:
        client.get("/api/auth/me")
    login(client, "anna.claes", "anna-password-1")
    with count_statements() as signed_in:
        client.get("/api/auth/me")
    assert anonymous.count <= 6
    assert signed_in.count <= 8
