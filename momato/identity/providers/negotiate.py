"""Windows sign-in by the app itself: HTTP Negotiate (Kerberos or NTLM), checked by Windows SSPI.

No IIS or other proxy takes part: the browser answers the server's `WWW-Authenticate: Negotiate`
challenge with a token that proves who is logged in to Windows, and Windows (SSPI, through
pyspnego) verifies it and names the account (`CORP\\jdoe`).

Kerberos needs one request. NTLM needs two, **on the same connection**: the context of a
half-finished handshake is kept here per connection, for a short time. Nothing is kept once a
handshake ends: the caller then starts an ordinary MoMaTo session.
"""

import logging
import sys
import threading
import time
from collections.abc import Callable, Hashable
from typing import Protocol, Self

import spnego
from spnego.exceptions import SpnegoError

from momato.config import Settings
from momato.domain.errors import InvalidCredentialsError
from momato.identity.providers.base import ExternalIdentity, NegotiateStep

logger = logging.getLogger("momato.sso")

HANDSHAKE_SECONDS = 30.0  # how long a half-finished handshake is remembered
MAX_PENDING = 1024  # half-finished handshakes kept at once; the oldest goes first

_NTLM_NEGOTIATE = b"NTLMSSP\x00\x01\x00\x00\x00"


class SecurityContext(Protocol):
    """The part of a pyspnego server context that is used here."""

    @property
    def complete(self) -> bool: ...

    @property
    def client_principal(self) -> str | None: ...

    def step(self, in_token: bytes | None = None) -> bytes | None: ...


def _sspi_context() -> SecurityContext:
    """Accepts Kerberos or NTLM, with the credentials of the account the app runs as."""
    return spnego.server(protocol="negotiate")


def _starts_handshake(token: bytes) -> bool:
    """A first token: GSS-API's initial token (SPNEGO or bare Kerberos), or NTLM's first message."""
    return token[:1] == b"\x60" or token.startswith(_NTLM_NEGOTIATE)


class NegotiateProvider:
    name = "windows"
    display_name = "Windows"

    def __init__(
        self,
        *,
        automatic: bool = True,
        strip_domain: bool = True,
        new_context: Callable[[], SecurityContext] = _sspi_context,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.automatic = automatic
        self.strip_domain = strip_domain
        self._new_context = new_context
        self._clock = clock
        self._pending: dict[Hashable, tuple[SecurityContext, float]] = {}
        self._lock = threading.Lock()  # endpoints run in a thread pool

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if sys.platform != "win32":
            raise ValueError("MOMATO_WINDOWS_AUTH needs a Windows server (it uses SSPI)")
        _sspi_context()  # a Windows that refuses fails the start, not the first sign-in
        return cls(
            automatic=settings.windows_auth_automatic,
            strip_domain=settings.windows_auth_strip_domain,
        )

    def step(self, connection: Hashable, token: bytes) -> NegotiateStep:
        """Feed the browser's token to the handshake on `connection`.

        Returns the token to answer with and, once Windows has verified the user, who it is.
        Raises InvalidCredentialsError when Windows refuses, or when the handshake this token
        continues is unknown (it took too long, or arrived on another connection).
        """
        context = self._take(connection)
        if _starts_handshake(token):
            context = self._new_context()
        elif context is None:
            raise InvalidCredentialsError("Windows sign-in was interrupted; try again")
        try:
            answer = context.step(token)
        except SpnegoError as error:
            logger.info("Windows sign-in refused: %s", error)
            raise InvalidCredentialsError("Windows did not accept this sign-in") from error
        if context.complete:
            return NegotiateStep(identity=self._identity(context.client_principal), token=answer)
        if not answer:
            raise InvalidCredentialsError("Windows did not accept this sign-in")
        self._keep(connection, context)
        return NegotiateStep(identity=None, token=answer)

    def _take(self, connection: Hashable) -> SecurityContext | None:
        now = self._clock()
        with self._lock:
            for key in [k for k, (_, deadline) in self._pending.items() if deadline < now]:
                del self._pending[key]
            pending = self._pending.pop(connection, None)
        return pending[0] if pending else None

    def _keep(self, connection: Hashable, context: SecurityContext) -> None:
        with self._lock:
            while len(self._pending) >= MAX_PENDING:
                del self._pending[next(iter(self._pending))]
            self._pending[connection] = (context, self._clock() + HANDSHAKE_SECONDS)

    def _identity(self, principal: str | None) -> ExternalIdentity:
        raw = (principal or "").strip()
        # SSPI names accounts CORP\jdoe; Kerberos libraries elsewhere say jdoe@CORP.EXAMPLE.
        login = raw.rsplit("\\", 1)[-1] if "\\" in raw else raw.split("@", 1)[0]
        if not login:
            raise InvalidCredentialsError("Windows did not say who is signing in")
        return ExternalIdentity(
            provider=self.name,
            subject=raw.lower(),
            display_name=login,  # only names accounts created on the fly; Windows tells no more
            username=(login if self.strip_domain else raw).lower(),
        )
