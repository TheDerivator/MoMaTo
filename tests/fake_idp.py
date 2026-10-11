"""An in-process OpenID Connect provider for tests: discovery, keys, authorization, tokens.

It plays both roles the real provider has: the HTTP API the app calls (`get_json`, `post_form`,
same interface as the app's HTTP client) and the sign-in page the browser visits (`approve`).
PKCE, single-use codes and signed ID tokens are real, so the app's checks are exercised.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from momato.identity.providers.oidc import OidcConfig, OidcError, OidcProvider

ISSUER = "https://idp.example.test/tenant/v2.0"
CLIENT_ID = "momato-tests"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeIdentityProvider:
    def __init__(self) -> None:
        self.key = new_key()
        self.kid = "key-1"
        self.codes: dict[str, dict[str, Any]] = {}
        self.token_audience = CLIENT_ID
        self.token_lifetime = 300
        self.nonce_override: str | None = None
        self.sign_with: rsa.RSAPrivateKey | None = None  # sign with a key it does not publish
        # Browser tests serve a real sign-in page and point this at it.
        self.authorization_endpoint = f"{ISSUER}/authorize"

    # ------------------------------------------------------------- provider API (for the app)

    def get_json(self, url: str) -> dict[str, Any]:
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return {
                "issuer": ISSUER,
                "authorization_endpoint": self.authorization_endpoint,
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/keys",
            }
        if url == f"{ISSUER}/keys":
            public = RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
            return {"keys": [public | {"kid": self.kid, "use": "sig", "alg": "RS256"}]}
        raise OidcError(f"unexpected request to {url}")

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        assert url == f"{ISSUER}/token", url
        grant = self.codes.pop(data.get("code", ""), None)
        if grant is None:
            raise OidcError("invalid_grant: unknown or used code")
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(data["code_verifier"].encode()).digest()
        )
        if challenge.rstrip(b"=").decode() != grant["code_challenge"]:
            raise OidcError("invalid_grant: PKCE verification failed")
        if data.get("redirect_uri") != grant["redirect_uri"] or data.get("client_id") != CLIENT_ID:
            raise OidcError("invalid_grant: redirect URI or client mismatch")
        now = int(time.time())
        claims = grant["claims"] | {
            "iss": ISSUER,
            "aud": self.token_audience,
            "iat": now,
            "exp": now + self.token_lifetime,
            "nonce": self.nonce_override or grant["nonce"],
        }
        return {"id_token": self.sign(claims), "token_type": "Bearer"}

    # ------------------------------------------------------------- the sign-in page (for the user)

    def approve(self, authorization_url: str, **claims: Any) -> dict[str, str]:
        """The user signs in; returns the query the provider sends back to the callback."""
        params = {k: v[0] for k, v in parse_qs(urlparse(authorization_url).query).items()}
        assert params["client_id"] == CLIENT_ID and params["code_challenge_method"] == "S256"
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "claims": claims,
            "code_challenge": params["code_challenge"],
            "redirect_uri": params["redirect_uri"],
            "nonce": params["nonce"],
        }
        return {"code": code, "state": params["state"]}

    def sign(self, claims: dict[str, Any], *, kid: str | None = None) -> str:
        key = self.sign_with or self.key
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid or self.kid})

    def rotate_keys(self) -> None:
        self.key = new_key()
        self.kid = f"key-{secrets.token_hex(3)}"


def fake_oidc_provider(idp: FakeIdentityProvider) -> OidcProvider:
    config = OidcConfig(
        name="entra",
        display_name="Microsoft",
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret="secret",
        subject_claim="oid",
    )
    return OidcProvider(config, http=idp)
