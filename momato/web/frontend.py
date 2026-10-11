"""Serve the single-page frontend: static files, and index.html for every app route.

App routes (`/projects`, `/timesheet`, ...) all return index.html so links and reloads work; the
browser-side router picks the view. The page's `<base href>` is set from the configured base path,
so the app also works when published under a prefix such as `/momato/`.
"""

from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# First path segments handled by the browser-side router (REQUIREMENTS SH-8; the router's own
# list lives in static/js/lib/routes.js and a test keeps the two equal).
APP_ROUTES = frozenset({"", "projects", "timesheet", "people", "plans", "profile", "admin"})


class RevalidatingStaticFiles(StaticFiles):
    """Static files that browsers must revalidate (cheap 304s), so a deploy is picked up at once.

    A file that is missing answers 404 with `no-store`: a CDN or browser that remembered the 404
    of a script would keep the page broken after the file arrives (a deploy missing a file).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            raise HTTPException(
                error.status_code, error.detail, headers={"Cache-Control": "no-store"}
            ) from error
        response.headers["Cache-Control"] = "no-cache"
        return response


def render_index(base_path: str) -> str:
    template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return template.replace("{{BASE_PATH}}", escape(base_path, quote=True))


def mount_frontend(app: FastAPI, *, base_path: str, reload_index: bool = False) -> None:
    """Static files under /static and the SPA fallback. Call after the API routes are added.

    `reload_index` re-reads index.html on every request (development); otherwise it is read once.
    """
    app.mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR), name="static")
    cached = render_index(base_path)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:  # pyright: ignore[reportUnusedFunction]
        first = path.split("/", 1)[0]
        if first == "api":
            return JSONResponse({"error": "not_found", "message": "no such endpoint"}, 404)
        status = 200 if first in APP_ROUTES else 404  # the page still renders its own "not found"
        index = render_index(base_path) if reload_index else cached
        return HTMLResponse(index, status_code=status, headers={"Cache-Control": "no-cache"})
