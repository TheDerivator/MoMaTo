"""SSO endpoints for redirect providers: start a sign-in, and the provider's callback.

Only mounted when a redirect provider (OpenID Connect) is configured.
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from momato.api.client import client_ip
from momato.api.cookies import cookie_secure, set_session_cookie
from momato.api.deps import AppSettings, Sso
from momato.domain.errors import DomainError
from momato.services.sso import REQUEST_LIFETIME, safe_return_path

router = APIRouter(prefix="/auth/sso", tags=["auth"])

STATE_COOKIE = "momato_sso_state"


def _redirect_uri(request: Request, settings: AppSettings, provider: str) -> str:
    base = settings.public_url.rstrip("/") + "/" if settings.public_url else str(request.base_url)
    return f"{base}api/auth/sso/{provider}/callback"


@router.get("/{provider}/start")
def start(
    provider: str, request: Request, sso: Sso, settings: AppSettings, next: str | None = None
) -> RedirectResponse:
    """Send the browser to the identity provider; it comes back to /callback."""
    url, state = sso.start(
        provider,
        redirect_uri=_redirect_uri(request, settings, provider),
        return_to=safe_return_path(next, settings.normalized_base_path),
    )
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=int(REQUEST_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request, settings),
        path="/",
    )
    return response


@router.get("/{provider}/callback")
def callback(
    provider: str,
    request: Request,
    sso: Sso,
    settings: AppSettings,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish the sign-in, set the session cookie, and go back to where the user started."""
    try:
        token, return_to = sso.finish(
            provider,
            state=state,
            browser_state=request.cookies.get(STATE_COOKIE),
            code=code,
            error=error,
            redirect_uri=_redirect_uri(request, settings, provider),
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except DomainError as problem:
        response = RedirectResponse(
            f"{settings.normalized_base_path}?sso_error={quote(str(problem))}", status_code=303
        )
    else:
        response = RedirectResponse(return_to, status_code=303)
        set_session_cookie(response, request, settings, token)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response
