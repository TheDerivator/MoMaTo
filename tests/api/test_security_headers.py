"""The security headers and the Content Security Policy on every kind of response. [§8.3]"""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import ClientFactory

REQUIRED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}


def check(response_headers: dict[str, str], what: str) -> None:
    for name, value in REQUIRED.items():
        assert response_headers.get(name) == value, (what, name)
    assert "permissions-policy" in response_headers, what
    policy = response_headers["content-security-policy"]
    assert "default-src 'none'" in policy, what
    assert "frame-ancestors 'none'" in policy, what
    assert "'unsafe-inline'" not in policy, what
    assert "'unsafe-eval'" not in policy, what


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/", 200),  # redirects client-side; the page itself
        ("/projects", 200),  # an app route: the page
        ("/projects/4102/remarks", 200),
        ("/admin/org", 200),
        ("/no/such/screen", 404),  # an unknown route: the page is not served for it
        ("/static/js/main.js", 200),
        ("/static/css/tokens.css", 200),
        ("/static/does-not-exist.js", 404),
        ("/api/health", 200),
        ("/api/auth/me", 200),
        ("/api/bootstrap", 200),
        ("/api/projects", 200),
        ("/api/projects/999999", 404),
        ("/api/admin/org", 403),  # a person without administration rights
        ("/api/projects?limit=0", 422),
        ("/api/exports/projects", 200),
        ("/api/exports/projects?format=xlsx", 200),
        ("/api/exports/time-entries?start=2026-09-28&end=2026-10-02", 200),
        ("/api/agent-guide", 200),
        ("/api/openapi.json", 200),
        ("/api/attachments/0123456789abcdef0123456789abcdef/x.png", 404),
        ("/api/no/such/endpoint", 404),
    ],
)
def test_every_kind_of_response_carries_the_headers(
    clients: ClientFactory, path: str, status: int
) -> None:
    anna: TestClient = clients("anna.claes")
    response = anna.get(path)
    assert response.status_code == status, (path, response.status_code)
    check(dict(response.headers), path)


def test_a_visitors_refusals_carry_them_too(clients: ClientFactory) -> None:
    visitor = clients()
    for path in ("/api/bootstrap", "/api/projects", "/api/exports/projects"):
        response = visitor.get(path)
        assert response.status_code == 401
        check(dict(response.headers), path)


def test_writes_and_their_failures_carry_them(clients: ClientFactory) -> None:
    anna = clients("anna.claes")
    refused = anna.post("/api/projects", json={})  # a person without edit rights: invalid body
    assert refused.status_code in {403, 422}
    check(dict(refused.headers), "POST /api/projects")
    csrf = anna.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert csrf.status_code == 403
    check(dict(csrf.headers), "a CSRF refusal")


def test_the_login_failure_and_the_throttle_carry_them(clients: ClientFactory) -> None:
    visitor = clients()
    wrong = visitor.post("/api/auth/login", json={"username": "anna.claes", "password": "x" * 12})
    assert wrong.status_code == 401
    check(dict(wrong.headers), "a failed login")


def test_the_api_docs_keep_every_header_but_the_policy(clients: ClientFactory) -> None:
    """Swagger UI loads from a CDN and runs inline code, so it has no CSP."""
    response = clients("anna.claes").get("/api/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    for name, value in REQUIRED.items():
        assert response.headers.get(name) == value
