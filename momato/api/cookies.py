"""Setting and clearing the session cookie (shared by password login and SSO sign-in)."""

from datetime import timedelta

from fastapi import Request, Response

from momato.config import Settings
from momato.identity.sessions import SESSION_COOKIE


def cookie_secure(request: Request, settings: Settings) -> bool:
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


def set_session_cookie(
    response: Response, request: Request, settings: Settings, token: str
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(timedelta(hours=settings.session_lifetime_hours).total_seconds()),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request, settings),
        path="/",
    )
