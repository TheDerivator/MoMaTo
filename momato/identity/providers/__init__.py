"""External identity providers (SSO). None are configured by default: built-in accounts only."""

from momato.identity.providers.base import (
    AmbientIdentityProvider,
    ExternalIdentity,
    IdentityProviders,
    NegotiateIdentityProvider,
    NegotiateStep,
    RedirectIdentityProvider,
)

__all__ = [
    "AmbientIdentityProvider",
    "ExternalIdentity",
    "IdentityProviders",
    "NegotiateIdentityProvider",
    "NegotiateStep",
    "RedirectIdentityProvider",
]
