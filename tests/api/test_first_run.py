"""A fresh installation has no organisation: an administrator names its root, once. [ADM-1] [SH-12]"""

from fastapi.testclient import TestClient

from momato.db.session import Database
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.factories import make_user
from tests.helpers import login

PASSWORD = "a-long-password-1"


def sign_in_admin(client: TestClient) -> None:
    assert login(client, "admin", TEST_ADMIN_PASSWORD).status_code == 200


def test_a_fresh_installation_answers_with_an_empty_org_tree(client: TestClient) -> None:
    """The page needs this to show its set-up screen instead of the shell."""
    sign_in_admin(client)
    body = client.get("/api/bootstrap").json()
    assert body["org"] == []
    assert body["me"]["permissions"]["org.manage"]["everywhere"] is True
    assert client.get("/api/admin/org").json() == []


def test_the_administrator_creates_the_root_once(client: TestClient) -> None:
    sign_in_admin(client)
    response = client.post("/api/admin/org", json={"name": "  Acme Corp  "})
    assert response.status_code == 201
    nodes = response.json()
    assert [(n["name"], n["parent_id"], n["is_department"]) for n in nodes] == [
        ("Acme Corp", None, False)
    ]
    assert [n["name"] for n in client.get("/api/bootstrap").json()["org"]] == ["Acme Corp"]
    entry = client.get("/api/admin/audit", params={"limit": 1}).json()[0]
    assert (entry["action"], entry["details"]["root"]) == ("org.node_created", True)

    second = client.post("/api/admin/org", json={"name": "Another"})
    assert second.status_code == 409
    assert len(client.get("/api/admin/org").json()) == 1

    branch = client.post("/api/admin/org", json={"parent_id": nodes[0]["id"], "name": "Plant"})
    assert branch.status_code == 201
    assert [n["name"] for n in branch.json()] == ["Acme Corp", "Plant"]


def test_a_root_needs_a_name(client: TestClient) -> None:
    sign_in_admin(client)
    assert client.post("/api/admin/org", json={}).status_code == 422
    assert client.post("/api/admin/org", json={"name": ""}).status_code == 422
    assert client.post("/api/admin/org", json={"name": "   "}).status_code == 422
    assert client.get("/api/admin/org").json() == []


def test_only_org_managers_may_name_the_organisation(
    client: TestClient, database: Database
) -> None:
    with database.session(write=True) as session:
        make_user(session, "Pat Plain", username="pat", password=PASSWORD)
    assert client.post("/api/admin/org", json={"name": "Acme"}).status_code == 401

    assert login(client, "pat", PASSWORD).status_code == 200
    assert client.post("/api/admin/org", json={"name": "Acme"}).status_code == 403
    body = client.get("/api/bootstrap").json()  # the page can say "not set up yet"
    assert body["org"] == []
    assert body["me"]["permissions"]["org.manage"]["everywhere"] is False
