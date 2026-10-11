"""Browser tests: a real server on a free port, driven by Playwright (Chromium).

Run with `uv run pytest -m e2e` (or `uv run python scripts/check.py --e2e`). Needs Chromium once:
`uv run playwright install chromium`.

Every test gets the same guard rails as helpers: `console_errors` (JavaScript errors),
`foreign_requests` (requests to another origin: MoMaTo loads nothing from outside, 8.3) and
`assert_accessible` (axe-core, WCAG 2.1 AA).
"""

import gc
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import uvicorn
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Page, Request
from starlette.types import ASGIApp

from momato.config import Settings
from momato.web import create_app
from tests.conftest import DEMO_PASSWORD

E2E_DIR = Path(__file__).resolve().parent

# When a browser drops a connection mid-request (a view navigates while its fetches are still in
# flight), Windows' asyncio proactor in the test server's thread may leave that socket for the
# garbage collector, which warns. Harmless, and not the app's code: only these two are ignored.
SERVER_SOCKET_FINALIZERS = (
    "ignore:Exception ignored while finalizing socket:pytest.PytestUnraisableExceptionWarning",
    "ignore:Exception ignored while calling deallocator <function _ProactorBasePipeTransport"
    ":pytest.PytestUnraisableExceptionWarning",
)

WCAG_21_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)
            for rule in SERVER_SOCKET_FINALIZERS:
                item.add_marker(pytest.mark.filterwarnings(rule))


@pytest.fixture
def live_server(settings: Settings) -> Iterator[str]:
    """Base URL (ending in "/") of a running server on an empty database."""
    yield from serve(create_app(settings))


@pytest.fixture
def sample_server(sample_settings: Settings) -> Iterator[str]:
    """Base URL of a running server on a copy of the sample data (everyone has DEMO_PASSWORD)."""
    yield from serve(create_app(sample_settings))


def serve(app: ASGIApp) -> Iterator[str]:
    """Run `app` on a free port in a background thread; yields its base URL."""
    # Port 0: the OS picks a free port at bind time (no race with other processes).
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", proxy_headers=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the test server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=10)
    # Finalize the server's leftover sockets now, while this test's warning filters apply, rather
    # than during whichever test the garbage collector happens to run in next.
    gc.collect()


def sign_in(page: Page, username: str, password: str = DEMO_PASSWORD) -> None:
    """Sign in through the login dialog and wait until it has gone."""
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_label("Username").fill(username)
    dialog.get_by_label("Password").fill(password)
    dialog.get_by_role("button", name="Log in").click()
    dialog.wait_for(state="detached")


def remember(
    page: Page, *, mode: str | None = None, look: str | None = None, tree: bool = True
) -> None:
    """Preset what a browser would have remembered: appearance and an expanded tree pane.

    Only applied when nothing is stored yet, so a reload shows what the app itself stored.
    """
    appearance = {"mode": mode, "look": look or "playful", "celebrate": True}
    ui = {"treeCollapsed": not tree, "navCollapsed": False, "collapsedNodes": []}
    page.add_init_script(
        "if (!localStorage.getItem('momato-appearance')) "
        f"localStorage.setItem('momato-appearance', {json.dumps(json.dumps(appearance))});"
        "if (!localStorage.getItem('momato-ui')) "
        f"localStorage.setItem('momato-ui', {json.dumps(json.dumps(ui))});"
    )


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """JavaScript errors seen by the page; tests assert it stays empty.

    Failed HTTP responses (e.g. a deliberate wrong password) are logged by the browser too; tests
    check those responses themselves, so they are not counted here.
    """
    errors: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error" and not message.text.startswith("Failed to load resource"):
            errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_default_timeout(10_000)
    return errors


@pytest.fixture
def foreign_requests(page: Page, live_server: str) -> list[str]:
    """URLs the page requested from any origin other than the app's; tests assert it stays empty."""
    own = urlsplit(live_server).netloc
    seen: list[str] = []

    def on_request(request: Request) -> None:
        parts = urlsplit(request.url)
        if parts.scheme in {"http", "https", "ws", "wss"} and parts.netloc != own:
            seen.append(request.url)

    page.on("request", on_request)
    return seen


@pytest.fixture
def assert_accessible(page: Page) -> Callable[[str], None]:
    """`assert_accessible("the project list")`: axe-core finds no WCAG 2.1 AA violation now."""

    def check(what: str) -> None:
        results = Axe().run(
            page,
            options={
                "runOnly": {"type": "tag", "values": WCAG_21_AA},
                "resultTypes": ["violations"],
            },
        )
        problems = [
            f"{v['id']} ({v['impact']}): {v['help']}: "
            + "; ".join(", ".join(node["target"]) for node in v["nodes"])
            for v in results.response["violations"]
        ]
        assert problems == [], f"accessibility violations on {what}:\n" + "\n".join(problems)

    return check
