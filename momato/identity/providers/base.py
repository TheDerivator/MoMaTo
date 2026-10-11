"""The contract every SSO provider fulfils, and the registry of configured providers.

Three shapes exist (AUTH-3):
- *ambient*: infrastructure in front of the app already authenticated the person and says so in a
  trusted request header (IIS Windows authentication, oauth2-proxy, ...). Checked per request.
- *redirect*: the browser is sent to the provider and comes back with proof (OpenID Connect).
- *negotiate*: the browser proves the Windows login to the app itself, in a short handshake on
  one endpoint (HTTP Negotiate: Kerberos or NTLM). No proxy, no redirect.
All produce an ExternalIdentity; `momato.identity.provisioning` maps it to a person.
"""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, Self

from momato.config import Settings


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    provider: str  # configured provider name, e.g. "entra"
    subject: str  # stable id at the provider (OIDC `sub`/`oid`); never an email
    email: str | None = None  # only claims the provider guarantees
    display_name: str | None = None
    groups: tuple[str, ...] = ()
    username: str | None = None  # a login name to match prepared people without an email


class AmbientIdentityProvider(Protocol):
    name: str
    display_name: str

    def identify(self, headers: Mapping[str, str], proxy: str | None) -> ExternalIdentity | None:
        """The identity asserted by the trusted proxy, or None if the request carries none.

        `proxy` is the trusted proxy the request came through (None: it came directly, so its
        headers prove nothing).
        """
        ...


class RedirectIdentityProvider(Protocol):
    name: str
    display_name: str

    def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        """Where to send the browser to sign in."""
        ...

    def complete(
        self, *, code: str, redirect_uri: str, code_verifier: str, nonce: str
    ) -> ExternalIdentity:
        """Redeem the authorization code and return the verified identity."""
        ...


@dataclass(frozen=True, slots=True)
class NegotiateStep:
    """One answer in a Negotiate handshake."""

    identity: ExternalIdentity | None  # who it is, once the handshake has finished
    token: bytes | None  # to send back to the browser (the next challenge, or the last word)


class NegotiateIdentityProvider(Protocol):
    name: str
    display_name: str
    automatic: bool  # the page tries to sign in by itself (otherwise only when asked)

    def step(self, connection: Hashable, token: bytes) -> NegotiateStep:
        """Take the handshake on `connection` one step further with the browser's token.

        Raises InvalidCredentialsError when the token is refused.
        """
        ...


@dataclass(frozen=True)
class IdentityProviders:
    ambient: Sequence[AmbientIdentityProvider] = ()
    redirect: Mapping[str, RedirectIdentityProvider] = field(
        default_factory=dict[str, RedirectIdentityProvider]
    )
    negotiate: NegotiateIdentityProvider | None = None

    @property
    def any(self) -> bool:
        return bool(self.ambient or self.redirect or self.negotiate)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Providers enabled by configuration; none by default (built-in accounts only)."""
        from momato.identity.providers.header import TrustedHeaderProvider
        from momato.identity.providers.oidc import OidcConfig, OidcProvider

        ambient: list[AmbientIdentityProvider] = []
        redirect: dict[str, RedirectIdentityProvider] = {}
        negotiate: NegotiateIdentityProvider | None = None
        if settings.oidc_client_id and settings.oidc_issuer:
            config = OidcConfig.from_settings(settings)
            redirect[config.name] = OidcProvider(config)
        if settings.trusted_header:
            ambient.append(TrustedHeaderProvider.from_settings(settings))
        if settings.windows_auth:
            from momato.identity.providers.negotiate import NegotiateProvider

            negotiate = NegotiateProvider.from_settings(settings)
        return cls(ambient=ambient, redirect=redirect, negotiate=negotiate)
