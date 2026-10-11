"""Security headers on every response, including a strict Content Security Policy.

The page may load scripts, styles, fonts and images only from this site. Its one inline script,
the import map in index.html, is allowed by its hash (computed from the page itself, so editing
the import map needs no second change). No inline styles, no framing, no plugins, no
content-type sniffing. `/api/docs` (Swagger UI, which loads its code from a CDN) gets the other
headers but no CSP. HSTS is left to the TLS-terminating proxy.
"""

import base64
import hashlib
import re
from collections.abc import Callable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_INLINE_SCRIPT = re.compile(
    r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
)

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
CSP_EXEMPT = ("/api/docs",)


def inline_script_hashes(page: str) -> list[str]:
    """CSP sources (`'sha256-...'`) for the inline scripts of an HTML page."""
    return [
        f"'sha256-{base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()}'"
        for body in _INLINE_SCRIPT.findall(page)
    ]


def content_security_policy(page: str) -> str:
    """The policy for the app: this site only, plus the page's own inline scripts by hash."""
    scripts = " ".join(["'self'", *inline_script_hashes(page)])
    return "; ".join(
        [
            "default-src 'none'",
            f"script-src {scripts}",
            "style-src 'self'",
            "img-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


class SecurityHeadersMiddleware:
    """Adds HEADERS and the CSP to every HTTP response that does not set them itself."""

    def __init__(self, app: ASGIApp, policy: Callable[[], str]) -> None:
        self.app = app
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        with_csp = not path.startswith(CSP_EXEMPT)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in HEADERS.items():
                    headers.setdefault(name, value)
                if with_csp:
                    headers.setdefault("Content-Security-Policy", self.policy())
            await send(message)

        await self.app(scope, receive, send_with_headers)
