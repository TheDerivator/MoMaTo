"""The org tree editor: add, rename, flag, move, reorder, delete; every endpoint with its
401 / 403 / 404 / 409 / 422 cases. [ADM-1] [AUTH-5] D-006
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import ClientFactory
from tests.api.test_projects import bootstrap, node_id


def tree_of(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/admin/org").json()


def children(nodes: list[dict[str, Any]], parent: int) -> list[str]:
    """Names of a node's children, in order."""
    kids = sorted((n for n in nodes if n["parent_id"] == parent), key=lambda n: n["position"])
    return [n["name"] for n in kids]


def positions(nodes: list[dict[str, Any]], parent: int) -> list[int]:
    return sorted(n["position"] for n in nodes if n["parent_id"] == parent)


def add(admin: TestClient, parent: str, name: str, **extra: Any) -> list[dict[str, Any]]:
    response = admin.post(
        "/api/admin/org",
        json={"parent_id": node_id(admin, parent), "name": name, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- who may


def test_a_visitor_gets_401_and_a_viewer_403(clients: ClientFactory) -> None:
    visitor, anna = clients(), clients("anna.claes")
    root = node_id(anna, "STL")
    requests = [
        ("get", "/api/admin/org", None),
        ("post", "/api/admin/org", {"parent_id": root, "name": "X"}),
        ("patch", f"/api/admin/org/{root}", {"name": "Y"}),
        ("delete", f"/api/admin/org/{root}", None),
    ]
    for method, url, body in requests:
        assert getattr(visitor, method)(url, **({"json": body} if body else {})).status_code == 401
        assert getattr(anna, method)(url, **({"json": body} if body else {})).status_code == 403


# ---------------------------------------------------------------- add


def test_a_branch_is_added_last_among_its_siblings_and_audited(admin: TestClient) -> None:
    before = bootstrap(admin)["org"]
    stl = node_id(admin, "STL")
    nodes = add(admin, "STL", "Metrology", is_department=True)
    assert children(nodes, stl) == [*children(before, stl), "Metrology"]
    created = next(n for n in nodes if n["name"] == "Metrology")
    assert created["is_department"] is True
    assert created["position"] == len(children(before, stl))
    assert any(n["name"] == "Metrology" for n in bootstrap(admin)["org"])
    entry = admin.get("/api/admin/audit", params={"limit": 1}).json()[0]
    assert (entry["action"], entry["target_type"], entry["target_id"]) == (
        "org.node_created",
        "org_node",
        str(created["id"]),
    )
    assert entry["details"]["parent"] == "STL"


def test_sibling_names_are_unique_but_other_branches_may_repeat_them(admin: TestClient) -> None:
    add(admin, "STL", "Metrology")
    clash = admin.post(
        "/api/admin/org", json={"parent_id": node_id(admin, "STL"), "name": "Metrology"}
    )
    assert clash.status_code == 409
    assert "already has a node named" in clash.json()["message"]
    again = admin.post(
        "/api/admin/org", json={"parent_id": node_id(admin, "R&D"), "name": "Metrology"}
    )
    assert again.status_code == 201


def test_adding_needs_a_known_parent_and_a_name(admin: TestClient) -> None:
    assert admin.post("/api/admin/org", json={"parent_id": 999_999, "name": "X"}).status_code == 404
    parent = node_id(admin, "STL")
    assert admin.post("/api/admin/org", json={"parent_id": parent, "name": ""}).status_code == 422
    assert admin.post("/api/admin/org", json={"parent_id": parent, "name": "  "}).status_code == 422
    # no parent means "the root": refused once the organisation has one (tests/api/test_first_run.py)
    assert admin.post("/api/admin/org", json={"name": "No parent"}).status_code == 409


# ---------------------------------------------------------------- rename and flag


def test_a_branch_is_renamed_and_flagged_as_a_department(admin: TestClient) -> None:
    quality = node_id(admin, "Quality")
    nodes = admin.patch(
        f"/api/admin/org/{quality}", json={"name": "Quality assurance", "is_department": True}
    ).json()
    changed = next(n for n in nodes if n["id"] == quality)
    assert (changed["name"], changed["is_department"]) == ("Quality assurance", True)
    entry = admin.get("/api/admin/audit", params={"limit": 1}).json()[0]
    assert entry["action"] == "org.node_updated"
    assert entry["details"]["renamed_from"] == "Quality"
    # a rename onto an existing sibling is refused
    process = node_id(admin, "Process")
    taken = admin.patch(f"/api/admin/org/{process}", json={"name": "Quality assurance"})
    assert taken.status_code == 409


def test_flagging_a_department_changes_what_own_department_means(
    clients: ClientFactory, admin: TestClient
) -> None:
    """[D-006] Anna's department is the nearest flagged node above her own node."""
    anna = clients("anna.claes")
    quality, stl = node_id(anna, "Quality"), node_id(anna, "STL")
    assert anna.get("/api/auth/me").json()["department_id"] == stl
    admin.patch(f"/api/admin/org/{quality}", json={"is_department": True})
    assert anna.get("/api/auth/me").json()["department_id"] == quality
    admin.patch(f"/api/admin/org/{quality}", json={"is_department": False})
    assert anna.get("/api/auth/me").json()["department_id"] == stl


def test_an_unknown_branch_is_404(admin: TestClient) -> None:
    assert admin.patch("/api/admin/org/999999", json={"name": "X"}).status_code == 404
    assert admin.delete("/api/admin/org/999999").status_code == 404


# ---------------------------------------------------------------- move and reorder


def test_a_branch_moves_under_another_and_both_sibling_lists_stay_contiguous(
    admin: TestClient,
) -> None:
    stl, rnd = node_id(admin, "STL"), node_id(admin, "R&D")
    quality = node_id(admin, "Quality")
    nodes = admin.patch(f"/api/admin/org/{quality}", json={"parent_id": rnd}).json()
    assert children(nodes, rnd)[-1] == "Quality"
    assert "Quality" not in children(nodes, stl)
    assert positions(nodes, stl) == list(range(len(children(nodes, stl))))
    assert positions(nodes, rnd) == list(range(len(children(nodes, rnd))))
    # people and projects move with the branch: Anna's node is the same node
    assert next(n for n in bootstrap(admin)["org"] if n["id"] == quality)["parent_id"] == rnd


def test_a_branch_is_placed_by_position_and_clamped_to_the_end(admin: TestClient) -> None:
    stl = node_id(admin, "STL")
    maintenance = node_id(admin, "Maintenance")
    nodes = admin.patch(f"/api/admin/org/{maintenance}", json={"position": 0}).json()
    assert children(nodes, stl)[0] == "Maintenance"
    assert positions(nodes, stl) == [0, 1, 2]
    nodes = admin.patch(f"/api/admin/org/{maintenance}", json={"position": 99}).json()
    assert children(nodes, stl)[-1] == "Maintenance"
    assert positions(nodes, stl) == [0, 1, 2]
    # a move with a position lands exactly there
    rnd = node_id(admin, "R&D")
    nodes = admin.patch(
        f"/api/admin/org/{maintenance}", json={"parent_id": rnd, "position": 1}
    ).json()
    assert children(nodes, rnd)[1] == "Maintenance"


def test_a_branch_cannot_move_into_itself_and_the_root_stays_put(admin: TestClient) -> None:
    stl, quality = node_id(admin, "STL"), node_id(admin, "Quality")
    root = next(n["id"] for n in bootstrap(admin)["org"] if n["parent_id"] is None)
    into_child = admin.patch(f"/api/admin/org/{stl}", json={"parent_id": quality})
    assert into_child.status_code == 422
    assert "into itself" in into_child.json()["message"]
    assert admin.patch(f"/api/admin/org/{stl}", json={"parent_id": stl}).status_code == 422
    root_move = admin.patch(f"/api/admin/org/{root}", json={"parent_id": stl})
    assert root_move.status_code == 422
    assert admin.patch(f"/api/admin/org/{root}", json={"position": 0}).status_code == 422
    # the root may be renamed
    assert admin.patch(f"/api/admin/org/{root}", json={"name": "Brightwater"}).status_code == 200


def test_a_move_onto_a_taken_name_is_refused(admin: TestClient) -> None:
    stl_quality = node_id(admin, "Quality")
    add(admin, "R&D", "Quality")
    clash = admin.patch(f"/api/admin/org/{stl_quality}", json={"parent_id": node_id(admin, "R&D")})
    assert clash.status_code == 409


# ---------------------------------------------------------------- delete


def test_an_unused_branch_is_deleted_and_the_rest_renumbered(admin: TestClient) -> None:
    stl = node_id(admin, "STL")
    add(admin, "STL", "Temp A")
    add(admin, "STL", "Temp B")
    nodes = add(admin, "STL", "Temp C")
    assert positions(nodes, stl) == [0, 1, 2, 3, 4, 5]
    temp_b = next(n["id"] for n in nodes if n["name"] == "Temp B")
    remaining = admin.delete(f"/api/admin/org/{temp_b}")
    assert remaining.status_code == 200
    nodes = remaining.json()
    assert "Temp B" not in children(nodes, stl)
    assert positions(nodes, stl) == [0, 1, 2, 3, 4]
    assert (
        admin.get("/api/admin/audit", params={"limit": 1}).json()[0]["action"] == "org.node_deleted"
    )


def test_a_branch_in_use_is_not_deleted_and_the_reasons_are_named(admin: TestClient) -> None:
    quality = node_id(admin, "Quality")
    refused = admin.delete(f"/api/admin/org/{quality}")
    assert refused.status_code == 409
    message = refused.json()["message"]
    assert "people" in message
    stl = node_id(admin, "STL")
    assert "branches below it" in admin.delete(f"/api/admin/org/{stl}").json()["message"]


def test_the_root_is_never_deleted(admin: TestClient) -> None:
    root = next(n["id"] for n in bootstrap(admin)["org"] if n["parent_id"] is None)
    response = admin.delete(f"/api/admin/org/{root}")
    assert response.status_code == 422


def test_rights_that_point_at_a_branch_keep_it_from_being_deleted(admin: TestClient) -> None:
    """Role assignments and default grants on a node count as use, so they are not orphaned."""
    add(admin, "STL", "Granted here")
    node = next(n["id"] for n in tree_of(admin) if n["name"] == "Granted here")
    person = next(p["id"] for p in bootstrap(admin)["people"] if p["name"] == "Anna Claes")
    assert (
        admin.post(
            f"/api/admin/people/{person}/assignments",
            json={"role_key": "project_admin", "scope_kind": "node", "node_id": node},
        ).status_code
        == 201
    )
    refused = admin.delete(f"/api/admin/org/{node}")
    assert refused.status_code == 409
    assert "role assignments" in refused.json()["message"]


@pytest.mark.parametrize("name", ["  Padded  ", "Padded"])
def test_names_are_stored_trimmed(admin: TestClient, name: str) -> None:
    nodes = add(admin, "STL", name)
    assert any(n["name"] == "Padded" for n in nodes)
