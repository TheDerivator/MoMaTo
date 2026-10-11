"""API tokens for AI agents: acting as the owner, scopes, never administration, refusals, revoking,
expiry, "via" marks on what a token wrote, administrators' view, the agent guide.
[TOK-1] [TOK-2] [TOK-3] [TOK-4]
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from momato.db.base import utcnow
from momato.db.models import ApiToken, User
from momato.db.models.people import UserStatus
from momato.db.session import Database
from momato.services.tokens import MAX_LIVE_TOKENS
from tests.api.conftest import ClientFactory
from tests.api.test_projects import bootstrap, person_id
from tests.api.test_timesheet import FRIDAY, WEEK, get, line_of, put, task_key

SENSORS = 4102  # Tomás Rivera coordinates it: his implicit rights are what a token must narrow


@pytest.fixture
def agent(app: FastAPI) -> Iterator[TestClient]:
    """A client like an AI agent's: no cookies, no CSRF header, only what the test sends."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def tomas(clients: ClientFactory) -> TestClient:
    """The coordinator of #4102, signed in on the browser."""
    return clients("tomas.rivera")


def issue(client: TestClient, name: str = "Claude Code", **body: Any) -> dict[str, Any]:
    response = client.post("/api/auth/tokens", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


def use(agent: TestClient, secret: str) -> TestClient:
    agent.headers["Authorization"] = f"Bearer {secret}"
    return agent


# ---------------------------------------------------------------- acting as the owner


def test_a_token_acts_as_its_owner_and_marks_what_it_writes(
    tomas: TestClient, agent: TestClient
) -> None:
    """[TOK-1] [TOK-3]"""
    created = issue(tomas, scope="write")
    assert created["secret"].startswith("mm_")
    assert created["secret"].startswith(created["token"]["prefix"])
    use(agent, created["secret"])

    me = agent.get("/api/auth/me").json()
    assert me["username"] == "tomas.rivera"
    assert me["api_token"] == {"name": "Claude Code", "scope": "write"}
    assert tomas.get("/api/auth/me").json()["api_token"] is None  # the browser has none

    # Writes need no CSRF header: the token alone decides (TOK-2).
    remark = agent.post(f"/api/projects/{SENSORS}/remarks", json={"body_md": "Summary by agent."})
    assert remark.status_code == 201, remark.text
    assert remark.json()["via"] == "Claude Code"
    version = agent.get(f"/api/projects/{SENSORS}").json()["version"]
    edit = agent.patch(f"/api/projects/{SENSORS}", json={"version": version, "status": "hold"})
    assert edit.status_code == 200, edit.text

    log = tomas.get(f"/api/projects/{SENSORS}/log").json()["items"]
    assert log[0]["field"] == "status"
    assert log[0]["via"] == "Claude Code"
    assert log[0]["actor"]["name"] == "Tomás Rivera"
    older = [e for e in log if e["field"] != "status"]
    assert all(e["via"] is None for e in older)  # what people did by hand has no mark

    by_hand = tomas.post(f"/api/projects/{SENSORS}/remarks", json={"body_md": "By hand."}).json()
    assert by_hand["via"] is None


def test_time_booked_through_a_token_is_marked(tomas: TestClient, agent: TestClient) -> None:
    """[TOK-3] Time entries show "via"."""
    use(agent, issue(tomas, scope="write")["secret"])
    week = get(tomas, WEEK)
    line = next(line for line in week["lines"] if line["kind"] == "project")
    task = task_key(week, line["key"], "General")

    response = put(agent, FRIDAY, line["key"], task, 120)
    assert response.status_code == 200, response.text
    marked = line_of(response.json(), line["key"])
    assert marked["minutes"][task][4] == 120
    assert marked["via"][task] == [None, None, None, None, "Claude Code"]
    # the owner sees the same mark in the browser; booking by hand removes it
    assert line_of(get(tomas, WEEK), line["key"])["via"][task][4] == "Claude Code"
    assert put(tomas, FRIDAY, line["key"], task, 60).status_code == 200
    assert line_of(get(tomas, WEEK), line["key"])["via"].get(task, [None] * 5)[4] is None


def test_edited_remarks_and_their_history_keep_the_marks(
    tomas: TestClient, agent: TestClient
) -> None:
    use(agent, issue(tomas, scope="write")["secret"])
    remark = tomas.post(f"/api/projects/{SENSORS}/remarks", json={"body_md": "First, by hand."})
    remark_id = remark.json()["id"]
    edited = agent.patch(f"/api/remarks/{remark_id}", json={"body_md": "Tidied by the agent."})
    assert edited.status_code == 200, edited.text
    assert edited.json()["via"] is None
    assert edited.json()["edited_via"] == "Claude Code"
    history = tomas.get(f"/api/remarks/{remark_id}/history").json()
    assert [v["via"] for v in history] == [None, "Claude Code"]


# ---------------------------------------------------------------- scopes


def test_a_read_token_reads_but_never_writes_even_for_the_coordinator(
    tomas: TestClient, agent: TestClient
) -> None:
    """[TOK-1] Tomás may edit #4102 as its coordinator; a read token of his may not."""
    created = issue(tomas)  # read is the default
    assert created["token"]["scope"] == "read"
    use(agent, created["secret"])
    project = agent.get(f"/api/projects/{SENSORS}")
    assert project.status_code == 200
    body = project.json()
    assert (body["can_edit"], body["can_comment"], body["can_delete"]) == (False, False, False)
    assert tomas.get(f"/api/projects/{SENSORS}").json()["can_edit"] is True

    me = agent.get("/api/auth/me").json()
    assert me["permissions"]["project.edit"] == {"everywhere": False, "node_ids": []}
    for method, url, payload in [
        ("post", f"/api/projects/{SENSORS}/remarks", {"body_md": "Hi"}),
        ("patch", f"/api/projects/{SENSORS}", {"version": body["version"], "status": "hold"}),
        (
            "put",
            f"/api/timesheet/{WEEK}/cells",
            {"day": "2026-10-05", "line": "x", "task": "y", "minutes": 60},
        ),
        ("post", f"/api/timesheet/{WEEK}/submit", None),
    ]:
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(agent, method)(url, **kwargs)
        assert response.status_code == 403, (method, url)
        assert response.json()["error"] == "permission_denied"


def test_a_read_token_still_sees_exactly_what_its_owner_sees(
    tomas: TestClient, agent: TestClient
) -> None:
    use(agent, issue(tomas)["secret"])
    assert agent.get("/api/projects").json()["total"] == tomas.get("/api/projects").json()["total"]
    assert agent.get("/api/bootstrap").status_code == 200
    assert agent.get("/api/timesheet").status_code == 200


def test_administration_is_never_possible_through_a_token(
    admin: TestClient, agent: TestClient
) -> None:
    """[TOK-1] A write token keeps the owner's rights except org.manage and users.manage."""
    use(agent, issue(admin, scope="write")["secret"])
    me = agent.get("/api/auth/me").json()
    assert me["permissions"]["users.manage"] == {"everywhere": False, "node_ids": []}
    assert me["permissions"]["org.manage"] == {"everywhere": False, "node_ids": []}
    assert me["permissions"]["project.delete"]["everywhere"] is True  # the rest stays
    for path in ("/api/admin/org", "/api/admin/people", "/api/admin/roles", "/api/admin/audit"):
        assert agent.get(path).status_code == 403, path
    created = agent.post("/api/admin/org", json={"parent_id": 1, "name": "X"})
    assert created.status_code == 403


# ---------------------------------------------------------------- refusals


def test_a_wrong_token_is_refused_instead_of_reading_as_a_visitor(agent: TestClient) -> None:
    """[TOK-2]"""
    for header in ("Bearer mm_nonsense", "Bearer ", "bearer mm_nonsense"):
        agent.headers["Authorization"] = header
        response = agent.get("/api/bootstrap")
        assert response.status_code == 401, header
        assert response.json()["error"] == "authentication_required"
        assert "token" in response.json()["message"]


def test_a_bearer_header_cannot_borrow_the_browser_session(tomas: TestClient) -> None:
    """[TOK-2] A write with a Bearer header skips the CSRF check, so it must never be judged
    by its cookies: a made-up token gets 401, not the signed-in person's rights."""
    del tomas.headers["X-CSRF-Token"]
    url = f"/api/projects/{SENSORS}/remarks"
    assert tomas.post(url, json={"body_md": "x"}).status_code == 403  # CSRF, as ever
    forged = tomas.post(url, json={"body_md": "x"}, headers={"Authorization": "Bearer mm_made_up"})
    assert forged.status_code == 401


def test_a_token_wins_over_the_browser_session(tomas: TestClient, clients: ClientFactory) -> None:
    secret = issue(tomas)["secret"]
    anna = clients("anna.claes")  # a browser signed in as somebody else
    me = anna.get("/api/auth/me", headers={"Authorization": f"Bearer {secret}"}).json()
    assert me["username"] == "tomas.rivera"
    assert me["api_token"]["scope"] == "read"


def test_revoking_expiry_and_suspension_end_a_token_at_once(
    tomas: TestClient, agent: TestClient, sample_database: Database
) -> None:
    """[TOK-1]"""
    first, second, third = (issue(tomas, name=n) for n in ("one", "two", "three"))
    use(agent, first["secret"])
    assert agent.get("/api/auth/me").status_code == 200
    assert tomas.delete(f"/api/auth/tokens/{first['token']['id']}").status_code == 204
    assert agent.get("/api/auth/me").status_code == 401
    assert tomas.delete(f"/api/auth/tokens/{first['token']['id']}").status_code == 404  # done

    use(agent, second["secret"])
    with sample_database.session(write=True) as session:
        session.execute(
            update(ApiToken)
            .where(ApiToken.id == second["token"]["id"])
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )
    assert agent.get("/api/auth/me").status_code == 401
    listed = {t["name"]: t for t in tomas.get("/api/auth/tokens").json()}
    assert set(listed) == {"two", "three"}
    assert listed["two"]["expired"] is True

    use(agent, third["secret"])
    assert agent.get("/api/auth/me").status_code == 200
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "tomas.rivera").values(status=UserStatus.SUSPENDED)
        )
    assert agent.get("/api/auth/me").status_code == 401


def test_tokens_are_managed_in_the_app_not_through_a_token(
    tomas: TestClient, agent: TestClient
) -> None:
    """[TOK-2] Tokens never manage tokens, and cannot change a password."""
    created = issue(tomas, scope="write")
    use(agent, created["secret"])
    assert agent.get("/api/auth/tokens").status_code == 403
    assert (
        agent.post("/api/auth/tokens", json={"name": "more", "scope": "write"}).status_code == 403
    )
    assert agent.delete(f"/api/auth/tokens/{created['token']['id']}").status_code == 403
    changed = agent.post(
        "/api/auth/password", json={"current_password": "x", "new_password": "y" * 20}
    )
    assert changed.status_code == 403


def test_visitors_cannot_have_tokens(clients: ClientFactory) -> None:
    visitor = clients()
    assert visitor.get("/api/auth/tokens").status_code == 401
    assert visitor.post("/api/auth/tokens", json={"name": "x"}).status_code == 401
    assert visitor.delete("/api/auth/tokens/1").status_code == 401


# ---------------------------------------------------------------- the tokens themselves


def test_the_secret_is_shown_once_and_only_its_hash_is_kept(
    tomas: TestClient, sample_database: Database
) -> None:
    created = issue(tomas, name="  Copilot  ", expires_in_days=None)
    assert created["token"]["name"] == "Copilot"
    assert created["token"]["expires_at"] is None
    listed = tomas.get("/api/auth/tokens").json()
    assert listed == [created["token"]]
    assert "secret" not in listed[0]
    with sample_database.session() as session:
        stored = session.scalars(select(ApiToken.token_hash)).all()
    assert created["secret"] not in stored
    assert len(stored[0]) == 64


def test_what_a_new_token_may_be(tomas: TestClient) -> None:
    for body in (
        {"name": ""},
        {"name": "x", "scope": "admin"},
        {"name": "x", "expires_in_days": 0},
        {"name": "x", "expires_in_days": 3651},
    ):
        assert tomas.post("/api/auth/tokens", json=body).status_code == 422, body
    expires = issue(tomas, expires_in_days=30)["token"]["expires_at"]
    assert expires.startswith((utcnow() + timedelta(days=30)).date().isoformat())


def test_at_most_so_many_live_tokens(tomas: TestClient) -> None:
    for n in range(MAX_LIVE_TOKENS):
        issue(tomas, name=f"t{n}")
    response = tomas.post("/api/auth/tokens", json={"name": "one more"})
    assert response.status_code == 422
    assert "revoke" in response.json()["message"]
    oldest = tomas.get("/api/auth/tokens").json()[-1]
    assert tomas.delete(f"/api/auth/tokens/{oldest['id']}").status_code == 204
    issue(tomas, name="one more")


def test_last_use_is_recorded(tomas: TestClient, agent: TestClient) -> None:
    created = issue(tomas)
    assert created["token"]["last_used_at"] is None
    use(agent, created["secret"]).get("/api/projects")
    used = tomas.get("/api/auth/tokens").json()[0]
    assert used["last_used_at"] is not None
    assert used["last_used_ip"] == "testclient"


def test_creating_and_revoking_are_audited_without_the_secret(
    tomas: TestClient, admin: TestClient
) -> None:
    created = issue(tomas, name="Laptop agent", scope="write")
    tomas.delete(f"/api/auth/tokens/{created['token']['id']}")
    entries = admin.get("/api/admin/audit", params={"action": "token.", "limit": 5}).json()
    assert [e["action"] for e in entries] == ["token.revoked", "token.created"]
    assert entries[1]["details"]["scope"] == "write"
    assert created["secret"] not in str(entries)


def test_administrators_see_and_revoke_anyones_tokens(
    tomas: TestClient, agent: TestClient, admin: TestClient, clients: ClientFactory
) -> None:
    use(agent, issue(tomas, name="Laptop agent")["secret"])
    person = person_id(tomas, "Tomás Rivera")
    anna = clients("anna.claes")
    assert anna.get(f"/api/admin/people/{person}/tokens").status_code == 403
    listed = admin.get(f"/api/admin/people/{person}/tokens").json()
    assert [t["name"] for t in listed] == ["Laptop agent"]
    assert admin.delete(f"/api/admin/people/{person}/tokens/{listed[0]['id']}").status_code == 204
    assert admin.get(f"/api/admin/people/{person}/tokens").json() == []
    assert admin.get("/api/admin/people/999999/tokens").status_code == 404
    assert admin.delete(f"/api/admin/people/{person}/tokens/{listed[0]['id']}").status_code == 404
    assert agent.get("/api/auth/me").status_code == 401


def test_a_person_sees_nothing_of_the_tokens_of_others(
    tomas: TestClient, clients: ClientFactory
) -> None:
    issue(tomas, name="mine")
    anna = clients("anna.claes")
    assert anna.get("/api/auth/tokens").json() == []
    other = issue(anna, name="annas")
    assert tomas.delete(f"/api/auth/tokens/{other['token']['id']}").status_code == 404
    assert bootstrap(tomas)["me"]["api_token"] is None


# ---------------------------------------------------------------- the agent guide (TOK-4)


def test_the_agent_guide(clients: ClientFactory) -> None:
    visitor = clients()  # the guide is public: it holds no data
    response = visitor.get("/api/agent-guide")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    guide = response.text
    assert "Authorization: Bearer" in guide
    assert "MOMATO_TOKEN" in guide
    assert "http://testserver/api/auth/me" in guide
    assert "http://testserver/profile" in guide
    assert "{{" not in guide
    assert "- `POST /api/projects/{number}/remarks`" in guide
    assert "- `GET /api/exports/projects`" in guide
    assert "- `GET /api/auth/me`" in guide
    for hidden in ("/api/admin/", "/api/auth/login", "/api/auth/tokens", "/api/auth/password"):
        assert hidden not in guide, hidden


def test_the_agent_guide_lists_every_endpoint_an_agent_may_use(app: FastAPI) -> None:
    """The endpoint list is generated from the OpenAPI document, so it cannot go stale."""
    guide = TestClient(app).get("/api/agent-guide").text
    hidden = {"auth", "tokens", "administration"}
    missing: list[str] = []
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            tag = (operation.get("tags") or ["other"])[0]
            if tag in hidden and (method, path) != ("get", "/api/auth/me"):
                continue
            if f"`{method.upper()} {path}`" not in guide:
                missing.append(f"{method.upper()} {path}")
    assert missing == []
