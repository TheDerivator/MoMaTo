"""Visual regression: one screenshot per screen and appearance, compared with the baseline images
in tests/e2e/baselines with a small tolerance. Run with `-m visual`; update the baselines on
purpose with `MOMATO_UPDATE_VISUAL=1 uv run pytest -m visual`. [APP-4] [§8.4]

Pinned date, seeded sample data, vendored fonts and reduced motion make the pages deterministic.
Where a page differs a lot (the audit log shows real time stamps) it is left out.
"""

import os
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Page, ViewportSize, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import remember, sign_in

pytestmark = pytest.mark.visual

BASELINES = Path(__file__).parent / "baselines"
FAILURES = Path(__file__).parent / "_failures"
UPDATE = os.environ.get("MOMATO_UPDATE_VISUAL") == "1"
CHANNEL_TOLERANCE = 12  # per colour channel, out of 255 (anti-aliasing, font hinting)
MAX_DIFFERING = 0.002  # at most this share of the pixels may differ
LOOKUP = [0] * (CHANNEL_TOLERANCE + 1) + [255] * (255 - CHANNEL_TOLERANCE)

SIZE: ViewportSize = {"width": 1280, "height": 860}
APPEARANCES = [("light", "playful"), ("dark", "playful"), ("light", "boring"), ("dark", "boring")]
SCREENS = [
    ("projects", "projects", ".table__link"),
    ("project-overview", "projects/4102", ".project-title"),
    ("project-planning", "projects/4102/planning", ".project-title"),
    ("project-people", "projects/4102/people", ".project-title"),
    ("project-remarks", "projects/4102/remarks", ".remark"),
    ("project-logbook", "projects/4102/logbook", ".log-entry"),
    ("project-details", "projects/4102/details", ".project-title"),
    ("timesheet", "timesheet", ".ts-card"),
    ("people-planned", "people", ".pp-person"),
    ("people-spent", "people?mode=spent&period=month", ".pp-person"),
    ("people-compare", "people?mode=compare&period=month", ".pp-person"),
    ("plans", "plans", ".plan-project"),
    ("profile", "profile", ".admin-card"),
]
ADMIN_SCREENS = [
    ("admin-org", "admin/org", ".org-row"),
    ("admin-people", "admin/people", ".admin-person"),
    ("admin-roles", "admin/roles", ".admin-role-head"),
]


def differing_share(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        return 1.0
    red, green, blue = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).split()
    strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = strongest.point(LOOKUP).histogram()[255]
    return changed / (a.width * a.height)


def check(page: Page, name: str) -> None:
    page.wait_for_timeout(250)  # let fonts and fills settle
    actual_path = FAILURES / f"{name}.png"
    baseline = BASELINES / f"{name}.png"
    shot = page.screenshot()
    if UPDATE or not baseline.exists():
        BASELINES.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(shot)
        if not UPDATE:
            pytest.fail(f"no baseline for {name}: wrote it; review it and run again")
        return
    FAILURES.mkdir(exist_ok=True)
    actual_path.write_bytes(shot)
    share = differing_share(Image.open(BytesIO(shot)), Image.open(baseline))
    if share <= MAX_DIFFERING:
        actual_path.unlink()
        return
    pytest.fail(
        f"{name} differs from its baseline in {share:.2%} of its pixels "
        f"(see {actual_path}; MOMATO_UPDATE_VISUAL=1 accepts the change)"
    )


@pytest.mark.parametrize(("mode", "look"), APPEARANCES, ids=lambda v: str(v))
def test_screens_look_as_they_did(sample_server: str, page: Page, mode: str, look: str) -> None:
    page.set_viewport_size(SIZE)
    page.emulate_media(reduced_motion="reduce")
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}timesheet")
    sign_in(page, "anna.claes")
    for name, path, ready in SCREENS:
        page.goto(f"{sample_server}{path}")
        expect(page.locator(ready).first).to_be_visible()
        check(page, f"{name}-{mode}-{look}")


@pytest.mark.parametrize(("mode", "look"), APPEARANCES, ids=lambda v: str(v))
def test_administration_looks_as_it_did(
    sample_server: str, page: Page, mode: str, look: str
) -> None:
    page.set_viewport_size(SIZE)
    page.emulate_media(reduced_motion="reduce")
    remember(page, mode=mode, look=look)
    page.goto(f"{sample_server}admin/org")
    sign_in(page, "admin", TEST_ADMIN_PASSWORD)
    for name, path, ready in ADMIN_SCREENS:
        page.goto(f"{sample_server}{path}")
        expect(page.locator(ready).first).to_be_visible()
        check(page, f"{name}-{mode}-{look}")
