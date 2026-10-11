"""Serving the frontend: app routes return the page, base path injection, static caching,
security headers and compression. [SH-8]"""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from momato.config import Settings
from momato.web import create_app
from momato.web.frontend import APP_ROUTES


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/projects",
        "/projects/4102",
        "/projects/4102/planning",
        "/timesheet",
        "/timesheet/2026-W41",
        "/people",
        "/plans",
        "/plans/3",
        "/profile",
        "/admin/people",
    ],
)
def test_app_routes_serve_the_page(client: TestClient, path: str) -> None:
    """[SH-8] The server answers every app route with the page, so pasted links work."""
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="app">' in response.text
    assert '<base href="/">' in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_a_missing_static_file_is_not_cacheable(client: TestClient) -> None:
    """A CDN remembering the 404 of a script would keep the page broken after the deploy is
    fixed (seen behind Cloudflare), so a missing file says `no-store`. [SH-8]"""
    response = client.get("/static/js/lib/not-there.js")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    existing = client.get("/static/js/lib/routes.js")
    assert existing.status_code == 200
    assert existing.headers["cache-control"] == "no-cache"


def test_the_servers_routes_are_the_routers_routes() -> None:
    """[SH-8] The first path segments the server answers with the page are the ones the browser
    router knows (static/js/lib/routes.js), plus the root that redirects to the projects."""
    source = (Path(__file__).parents[2] / "momato/static/js/lib/routes.js").read_text("utf-8")
    heads = re.search(r"export const HEADS = \[(.*?)\];", source, re.DOTALL)
    assert heads is not None
    names = set(re.findall(r'"([a-z]+)"', heads.group(1)))
    assert names == APP_ROUTES - {""}


def test_unknown_pages_still_render_the_app_with_404(client: TestClient) -> None:
    """The server still answers with the page, which renders its own "not found" view."""
    response = client.get("/no/such/page")
    assert response.status_code == 404
    assert '<div id="app">' in response.text


def test_unknown_api_paths_answer_json(client: TestClient) -> None:
    response = client.get("/api/no/such/endpoint")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("/momato", "/momato/"), ("tools/momato/", "/tools/momato/"), ("", "/")],
)
def test_base_path_is_normalized_and_injected(
    settings: Settings, configured: str, expected: str
) -> None:
    """[SH-8] The app works under a URL prefix (MOMATO_BASE_PATH)."""
    app = create_app(settings.model_copy(update={"base_path": configured}))
    with TestClient(app) as client:
        assert f'<base href="{expected}">' in client.get("/projects").text


def test_static_files_are_revalidated(client: TestClient) -> None:
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "javascript" in response.headers["content-type"]


def test_security_headers_on_pages_api_and_static_files(client: TestClient) -> None:
    for path in ("/projects", "/api/health", "/static/js/main.js", "/api/no/such/endpoint"):
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["x-frame-options"] == "DENY", path
        assert headers["referrer-policy"] == "same-origin", path
        assert "frame-ancestors 'none'" in headers["content-security-policy"], path


def test_the_policy_allows_exactly_the_pages_inline_import_map(client: TestClient) -> None:
    page = client.get("/projects")
    policy = dict(
        directive.strip().split(" ", 1)
        for directive in page.headers["content-security-policy"].split(";")
    )
    assert policy["default-src"] == "'none'"
    assert policy["style-src"] == "'self'"  # no inline styles
    [import_map] = re.findall(r'<script type="importmap">(.*?)</script>', page.text, re.DOTALL)
    digest = base64.b64encode(hashlib.sha256(import_map.encode()).digest()).decode()
    assert policy["script-src"] == f"'self' 'sha256-{digest}'"


def test_the_api_docs_keep_working(client: TestClient) -> None:
    """Swagger UI loads from a CDN and runs inline code: it gets no CSP (the rest still applies)."""
    headers = client.get("/api/docs").headers
    assert "content-security-policy" not in headers
    assert headers["x-content-type-options"] == "nosniff"


def _with_payloads(settings: Settings) -> TestClient:
    """The real app plus two routes of known size, ahead of the SPA fallback."""
    app = create_app(settings)

    def payload(size: int) -> Route:
        return Route(f"/payload/{size}", lambda _request: PlainTextResponse("x" * size))

    app.router.routes[:0] = [payload(5000), payload(100)]
    return TestClient(app)


def test_large_responses_are_compressed(settings: Settings) -> None:
    """Responses over 1 kB are compressed (REQUIREMENTS 8.5)."""
    with _with_payloads(settings) as client:
        response = client.get("/payload/5000", headers={"Accept-Encoding": "gzip"})
        assert response.headers["content-encoding"] == "gzip"
        assert response.text == "x" * 5000  # the client decompresses transparently


def test_small_responses_are_not_compressed(settings: Settings) -> None:
    with _with_payloads(settings) as client:
        response = client.get("/payload/100", headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in response.headers
