"""Windows sign-in endpoint: the HTTP Negotiate handshake (Kerberos or NTLM) with the browser.

Only mounted when MOMATO_WINDOWS_AUTH is on. The page calls it with a plain fetch; the browser
itself answers the 401 challenges, so the page only ever sees the end: the signed-in user and a
session cookie, or a 401 it could not answer.
"""

import base64
import binascii

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from momato.api.client import client_ip, connection_id
from momato.api.cookies import set_session_cookie
from momato.api.deps import AppSettings, Providers, Sso
from momato.api.errors import error_response
from momato.domain.errors import InvalidCredentialsError, NotFoundError
from momato.schemas.auth import Me

router = APIRouter(prefix="/auth", tags=["auth"])

SCHEME = "Negotiate"
CHALLENGE_CODE = "windows_sign_in_required"  # the page tells challenges from refusals by this


def _challenge(message: str, token: bytes | None = None) -> JSONResponse:
    """401 that asks the browser for the next token (its body is only seen if it gives up)."""
    response = error_response(401, CHALLENGE_CODE, message)
    response.headers["WWW-Authenticate"] = _authenticate(token)
    return response


def _authenticate(token: bytes | None) -> str:
    return f"{SCHEME} {base64.b64encode(token).decode('ascii')}" if token else SCHEME


def _token(authorization: str | None) -> bytes | None:
    """The token in `Authorization: Negotiate <base64>`, or None when there is none to use."""
    scheme, _, value = (authorization or "").strip().partition(" ")
    if scheme.lower() != SCHEME.lower():
        return None
    try:
        return base64.b64decode(value.strip(), validate=True) or None
    except binascii.Error:
        return None


@router.post("/windows", response_model=Me)
def windows_sign_in(
    request: Request, response: Response, sso: Sso, settings: AppSettings, providers: Providers
) -> Me | JSONResponse:
    """Sign in as the Windows user the browser proves to be; answers 401 until it has."""
    provider = providers.negotiate
    if provider is None:
        raise NotFoundError("Windows sign-in is not switched on")
    token = _token(request.headers.get("authorization"))
    if token is None:
        return _challenge("sign in with your Windows account")
    try:
        step = provider.step(connection_id(request), token)
    except InvalidCredentialsError as refused:
        return _challenge(str(refused))  # the browser may ask for a user name and password
    if step.identity is None:
        return _challenge("sign in with your Windows account", step.token)
    principal, session_token = sso.sign_in(
        step.identity,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, request, settings, session_token)
    if step.token:  # Kerberos and SPNEGO end with a word for the browser (mutual authentication)
        response.headers["WWW-Authenticate"] = _authenticate(step.token)
    return Me.build(principal, providers)
