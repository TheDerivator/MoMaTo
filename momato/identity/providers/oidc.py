"""OpenID Connect sign-in (authorization code flow with PKCE), e.g. Microsoft Entra ID.

The ID token is verified locally: signature against the provider's published keys (JWKS), issuer,
audience (our client id), expiry and the nonce we sent. Provider metadata and keys are fetched
from the issuer's discovery document and cached; unknown key ids trigger one key refresh (key
rotation). HTTP goes through a small injectable client so tests can stand in for the provider.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, Self, cast

import jwt

from momato.config import Settings
from momato.domain.errors import InvalidCredentialsError
from momato.identity.providers.base import ExternalIdentity

ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]
METADATA_TTL_SECONDS = 3600


class OidcError(InvalidCredentialsError):
    """Sign-in with the external provider failed (message safe to show)."""


class HttpClient(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]: ...


class UrllibHttpClient:
    """Standard-library HTTP for the three calls OIDC needs (discovery, keys, token)."""

    def __init__(self, timeout: float = 10) -> None:
        self.timeout = timeout

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise OidcError(
                f"the identity provider refused the request ({error.code}): {detail}"
            ) from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise OidcError(f"the identity provider cannot be reached: {error}") from error

    def get_json(self, url: str) -> dict[str, Any]:
        return self._send(urllib.request.Request(url, headers={"Accept": "application/json"}))  # noqa: S310

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        body = urllib.parse.urlencode(data).encode()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return self._send(urllib.request.Request(url, data=body, headers=headers, method="POST"))  # noqa: S310


@dataclass(frozen=True)
class OidcConfig:
    name: str
    display_name: str
    issuer: str
    client_id: str
    client_secret: str | None
    scopes: str = "openid profile email"
    subject_claim: str = "sub"
    email_claims: tuple[str, ...] = ("email", "preferred_username", "upn")
    groups_claim: str = "groups"

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if not (settings.oidc_issuer and settings.oidc_client_id):
            raise ValueError("MOMATO_OIDC_ISSUER and MOMATO_OIDC_CLIENT_ID must both be set")
        secret = settings.oidc_client_secret
        return cls(
            name=settings.oidc_name,
            display_name=settings.oidc_display_name,
            issuer=settings.oidc_issuer.rstrip("/"),
            client_id=settings.oidc_client_id,
            client_secret=secret.get_secret_value() if secret else None,
            scopes=settings.oidc_scopes,
            subject_claim=settings.oidc_subject_claim,
            email_claims=tuple(
                c.strip() for c in settings.oidc_email_claims.split(",") if c.strip()
            ),
            groups_claim=settings.oidc_groups_claim,
        )


class OidcProvider:
    def __init__(self, config: OidcConfig, http: HttpClient | None = None) -> None:
        self.config = config
        self.name = config.name
        self.display_name = config.display_name
        self.http = http or UrllibHttpClient()
        self._metadata: dict[str, Any] | None = None
        self._metadata_at = 0.0
        self._keys: dict[str, jwt.PyJWK] = {}

    # ------------------------------------------------------------------ metadata and keys

    def metadata(self) -> dict[str, Any]:
        if self._metadata is None or time.monotonic() - self._metadata_at > METADATA_TTL_SECONDS:
            url = f"{self.config.issuer}/.well-known/openid-configuration"
            metadata = self.http.get_json(url)
            for required in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
                if required not in metadata:
                    raise OidcError(f"the identity provider's configuration lacks {required}")
            self._metadata = metadata
            self._metadata_at = time.monotonic()
        return self._metadata

    def _load_keys(self) -> None:
        jwks = self.http.get_json(self.metadata()["jwks_uri"])
        self._keys = {}
        for data in jwks.get("keys", []):
            if data.get("use", "sig") != "sig" or "kid" not in data:
                continue
            try:
                self._keys[data["kid"]] = jwt.PyJWK(data)
            except jwt.PyJWKError:
                continue  # key types we don't use

    def _key(self, kid: str | None) -> jwt.PyJWK:
        if kid is None:
            raise OidcError("the sign-in token has no key id")
        if kid not in self._keys:
            self._load_keys()  # the provider may have rotated its keys
        if kid not in self._keys:
            raise OidcError("the sign-in token was signed with an unknown key")
        return self._keys[kid]

    # ------------------------------------------------------------------ the flow

    def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.config.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        endpoint = self.metadata()["authorization_endpoint"]
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{urllib.parse.urlencode(params)}"

    def complete(
        self, *, code: str, redirect_uri: str, code_verifier: str, nonce: str
    ) -> ExternalIdentity:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": code_verifier,
        }
        if self.config.client_secret:
            form["client_secret"] = self.config.client_secret
        tokens = self.http.post_form(self.metadata()["token_endpoint"], form)
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("the identity provider sent no ID token")
        return self.identity_from(self.verify(id_token, nonce=nonce))

    def verify(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        """Check signature, issuer, audience, expiry and nonce; return the claims."""
        try:
            header = jwt.get_unverified_header(id_token)
            algorithm = header.get("alg")
            if algorithm not in ALLOWED_ALGORITHMS:
                raise OidcError(f"unsupported token signature algorithm {algorithm!r}")
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=self._key(header.get("kid")),
                algorithms=[algorithm],
                audience=self.config.client_id,
                issuer=self.metadata()["issuer"],
                options={"require": ["exp", "iat", "iss", "aud"]},
                leeway=60,
            )
        except jwt.PyJWTError as error:
            raise OidcError(f"the sign-in token is not valid: {error}") from error
        if claims.get("nonce") != nonce:
            raise OidcError("the sign-in token does not belong to this sign-in (nonce mismatch)")
        return claims

    def identity_from(self, claims: dict[str, Any]) -> ExternalIdentity:
        subject = claims.get(self.config.subject_claim)
        if not subject:
            raise OidcError(f"the sign-in token has no {self.config.subject_claim!r} claim")
        email = next(
            (
                str(claims[c])
                for c in self.config.email_claims
                if claims.get(c) and "@" in str(claims[c])
            ),
            None,
        )
        reported: object = claims.get(self.config.groups_claim)
        groups = cast("list[object]", reported) if isinstance(reported, list) else []
        return ExternalIdentity(
            provider=self.name,
            subject=str(subject),
            email=email,
            display_name=claims.get("name"),
            groups=tuple(str(g) for g in groups),
        )
