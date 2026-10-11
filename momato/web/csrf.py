"""CSRF protection (double-submit cookie) as ASGI middleware (AUTH-1).

Every response makes sure the browser has a random `momato_csrf` cookie (readable by the page's
JavaScript). Every state-changing request to `/api/` must echo it in the `X-CSRF-Token` header. A
foreign site can make the browser send the cookie, but it cannot read it to set the header.
Session cookies are also SameSite=Lax, so this is a second layer.

Requests with an API token (`Authorization: Bearer`, TOK-2) are exempt: such a request is judged
by its token alone, never by cookies, and a foreign page cannot make a browser add that header
(it would need CORS, which the app does not allow).
"""

import secrets

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSRF_COOKIE = "momato_csrf"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware:
    def __init__(self, app: ASGIApp, *, cookie_secure: bool | None = None) -> None:
        self.app = app
        self.cookie_secure = cookie_secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        cookie = request.cookies.get(CSRF_COOKIE)
        bearer = request.headers.get("authorization", "")[:7].lower() == "bearer "
        if (
            request.method not in _SAFE_METHODS
            and request.url.path.startswith("/api/")
            and not bearer
        ):
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not secrets.compare_digest(cookie.encode(), header.encode()):
                response = JSONResponse(
                    {"error": "csrf_failed", "message": "missing or wrong X-CSRF-Token header"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        if cookie:
            await self.app(scope, receive, send)
            return

        token = secrets.token_urlsafe(32)
        secure = (
            self.cookie_secure if self.cookie_secure is not None else request.url.scheme == "https"
        )
        cookie_value = f"{CSRF_COOKIE}={token}; Path=/; SameSite=Lax" + (
            "; Secure" if secure else ""
        )

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("set-cookie", cookie_value)
            await send(message)

        await self.app(scope, receive, send_with_cookie)
