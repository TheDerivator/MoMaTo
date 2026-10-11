"""Authentication use cases: who is calling, log in, log out, change password.

Order of identification for a request: an API token when the request carries one (it decides
alone), else a valid session cookie, else an ambient SSO provider (trusted proxy header)
when one is configured, else the anonymous principal.
"""

from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta

from sqlalchemy.orm import Session

from momato.config import Settings
from momato.db.models import User
from momato.domain.errors import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    PermissionDeniedError,
    RuleViolationError,
)
from momato.identity import api_tokens, password_login, provisioning, sessions
from momato.identity.passwords import hash_password, password_problems, verify_password
from momato.identity.principal import Principal, anonymous_principal, principal_for_user
from momato.identity.providers import IdentityProviders
from momato.services import audit


class AuthService:
    def __init__(
        self, session: Session, settings: Settings, providers: IdentityProviders | None = None
    ) -> None:
        self.session = session
        self.settings = settings
        self.providers = providers or IdentityProviders()

    @property
    def session_lifetime(self) -> timedelta:
        return timedelta(hours=self.settings.session_lifetime_hours)

    def principal_for_request(
        self,
        *,
        session_token: str | None,
        api_token: str | None = None,
        headers: Mapping[str, str] | None = None,
        proxy: str | None = None,
    ) -> Principal:
        """A request with a Bearer token is judged by that token alone: a bad one is refused,
        never read as the cookie's person or as a visitor (TOK-2)."""
        if api_token is not None:
            principal = api_tokens.principal_for_secret(self.session, api_token)
            if principal is None:
                raise AuthenticationRequiredError("the API token is unknown, revoked or expired")
            return principal
        user = sessions.user_for_token(self.session, session_token)
        if user is not None:
            return principal_for_user(self.session, user)
        if ambient := self._ambient_user(headers or {}, proxy):
            person, provider = ambient
            return replace(principal_for_user(self.session, person), ambient_provider=provider)
        return anonymous_principal(self.session)

    def _ambient_user(
        self, headers: Mapping[str, str], proxy: str | None
    ) -> tuple[User, str] | None:
        """The person a trusted proxy vouches for on this request, if one is configured."""
        for provider in self.providers.ambient:
            identity = provider.identify(headers, proxy)
            if identity is None:
                continue
            user, outcome = provisioning.resolve_user(
                self.session, identity, self.settings.sso_unknown_users
            )
            if outcome != "known":
                audit.record(
                    self.session,
                    f"user.sso_{outcome}",
                    actor_user_id=user.id,
                    target_type="user",
                    target_id=user.id,
                    provider=identity.provider,
                )
            if self.session.new or self.session.dirty:
                self.session.commit()
            return user, provider.name
        return None

    def login(
        self, username: str, password: str, *, ip_address: str | None, user_agent: str | None
    ) -> tuple[Principal, str]:
        """Check the password and start a session. Returns the principal and the cookie token."""
        policy = password_login.ThrottlePolicy(
            max_failures_per_user=self.settings.login_max_failures_per_user,
            max_failures_per_ip=self.settings.login_max_failures_per_ip,
            window=timedelta(minutes=self.settings.login_throttle_minutes),
        )
        try:
            user = password_login.authenticate(
                self.session, username, password, ip_address=ip_address, policy=policy
            )
        except InvalidCredentialsError:
            self.session.commit()  # keep the record of the failed attempt
            raise
        token = sessions.start_session(
            self.session,
            user,
            lifetime=self.session_lifetime,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        sessions.purge_expired(self.session)
        audit.record(self.session, "auth.login", actor_user_id=user.id, method="password")
        self.session.commit()
        return principal_for_user(self.session, user), token

    def logout(self, session_token: str | None) -> None:
        sessions.end_session(self.session, session_token)
        self.session.commit()

    def change_password(
        self,
        principal: Principal,
        *,
        current_password: str,
        new_password: str,
        session_token: str | None,
    ) -> None:
        """Change the caller's own password; other sessions of this account are logged out."""
        if principal.token_id is not None:
            raise PermissionDeniedError(
                "a password is changed in MoMaTo itself, not through a token"
            )
        user = self.session.get(User, principal.user_id)
        if user is None or principal.is_anonymous:
            raise InvalidCredentialsError("log in first")
        if not verify_password(user.password_hash, current_password):
            raise InvalidCredentialsError("the current password is wrong")
        if problems := password_problems(new_password):
            raise RuleViolationError("new password " + "; ".join(problems))
        if new_password == current_password:
            raise RuleViolationError("new password must differ from the current one")
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        sessions.end_all_sessions(self.session, user.id, except_token=session_token)
        audit.record(
            self.session,
            "user.password_changed",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
        )
        self.session.commit()
