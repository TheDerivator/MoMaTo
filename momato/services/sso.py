"""SSO sign-ins that start a session: the OpenID Connect round trip, and Windows sign-in.

Each redirect sign-in gets a random state (stored hashed, single use, 10 minutes), a nonce bound
into the ID token, and a PKCE code verifier. The finished identity goes through the same
provisioning as every SSO login (pre-provisioned accounts, suspension, group mappings). So does
an identity that Windows sign-in (Negotiate) has verified: `sign_in` starts its session.
"""

import base64
import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from momato.config import Settings
from momato.db.base import utcnow
from momato.db.models import SsoRequest, User
from momato.domain.errors import InvalidCredentialsError, NotFoundError
from momato.identity import provisioning, sessions
from momato.identity.principal import Principal, principal_for_user
from momato.identity.providers import (
    ExternalIdentity,
    IdentityProviders,
    RedirectIdentityProvider,
)
from momato.services import audit

REQUEST_LIFETIME = timedelta(minutes=10)


def safe_return_path(value: str | None, default: str) -> str:
    """Only paths on this site: no scheme, no host, no protocol-relative `//` (no open redirect)."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return default
    return value


def pkce_pair() -> tuple[str, str]:
    """(code verifier, S256 code challenge) as in RFC 7636."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


class SsoService:
    def __init__(self, session: Session, settings: Settings, providers: IdentityProviders) -> None:
        self.session = session
        self.settings = settings
        self.providers = providers

    def _provider(self, name: str) -> RedirectIdentityProvider:
        provider = self.providers.redirect.get(name)
        if provider is None:
            raise NotFoundError(f"no sign-in provider {name}")
        return provider

    def start(self, provider_name: str, *, redirect_uri: str, return_to: str) -> tuple[str, str]:
        """Returns (URL to send the browser to, state to bind to the browser in a cookie)."""
        provider = self._provider(provider_name)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(24)
        verifier, challenge = pkce_pair()
        self.session.execute(
            delete(SsoRequest).where(SsoRequest.created_at < utcnow() - REQUEST_LIFETIME)
        )
        self.session.add(
            SsoRequest(
                state_hash=_hash(state),
                provider=provider_name,
                nonce=nonce,
                code_verifier=verifier,
                return_to=return_to,
            )
        )
        url = provider.authorization_url(
            redirect_uri=redirect_uri, state=state, nonce=nonce, code_challenge=challenge
        )
        self.session.commit()
        return url, state

    def finish(
        self,
        provider_name: str,
        *,
        state: str | None,
        browser_state: str | None,
        code: str | None,
        error: str | None,
        redirect_uri: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[str, str]:
        """Returns (session token, where to send the browser)."""
        provider = self._provider(provider_name)
        if not state or not browser_state or not secrets.compare_digest(state, browser_state):
            raise InvalidCredentialsError("this sign-in was not started in this browser; try again")
        request = self.session.scalars(
            select(SsoRequest).where(
                SsoRequest.state_hash == _hash(state), SsoRequest.provider == provider_name
            )
        ).one_or_none()
        if request is None or request.created_at < utcnow() - REQUEST_LIFETIME:
            raise InvalidCredentialsError("this sign-in has expired; try again")
        nonce, verifier, return_to = request.nonce, request.code_verifier, request.return_to
        self.session.delete(request)  # single use, whatever happens next
        self.session.commit()
        if error:
            raise InvalidCredentialsError(f"sign-in was cancelled or refused ({error})")
        if not code:
            raise InvalidCredentialsError("the identity provider sent no authorization code")

        identity = provider.complete(
            code=code, redirect_uri=redirect_uri, code_verifier=verifier, nonce=nonce
        )
        _, token = self._start_session(identity, ip_address=ip_address, user_agent=user_agent)
        return token, return_to

    def sign_in(
        self, identity: ExternalIdentity, *, ip_address: str | None, user_agent: str | None
    ) -> tuple[Principal, str]:
        """Start a session for an identity its provider has verified (Windows sign-in).

        Returns the principal and the cookie token.
        """
        user, token = self._start_session(identity, ip_address=ip_address, user_agent=user_agent)
        return principal_for_user(self.session, user), token

    def _start_session(
        self, identity: ExternalIdentity, *, ip_address: str | None, user_agent: str | None
    ) -> tuple[User, str]:
        user, outcome = provisioning.resolve_user(
            self.session, identity, self.settings.sso_unknown_users
        )
        self.session.flush()
        token = sessions.start_session(
            self.session,
            user,
            lifetime=timedelta(hours=self.settings.session_lifetime_hours),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        audit.record(
            self.session,
            "auth.login",
            actor_user_id=user.id,
            method=identity.provider,
            account=outcome,
        )
        self.session.commit()
        return user, token
