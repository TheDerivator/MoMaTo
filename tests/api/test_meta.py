"""Health endpoint, API docs and the static app shell are served."""

from fastapi.testclient import TestClient

from momato import __version__


def test_health_reports_ok_and_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_openapi_docs_are_served_under_api(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    document = client.get("/api/openapi.json").json()
    assert document["info"]["title"] == "MoMaTo"
    assert "/api/health" in document["paths"]


def test_root_serves_the_app_shell(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
