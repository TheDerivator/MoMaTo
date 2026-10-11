"""API token use cases (TOK-1, TOK-2): your own tokens (list, create, revoke) and, for people who
manage users, anyone's (list, revoke).

Tokens are made and revoked by people signed in to MoMaTo itself, never through a token: a leaked
read token cannot mint a write token, nor keep itself alive.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.models import ApiToken, User
from momato.domain.access import Permission
from momato.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
    RuleViolationError,
)
from momato.identity import api_tokens
from momato.identity.principal import Principal
from momato.schemas.tokens import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from momato.services import audit

MAX_LIVE_TOKENS = 25  # per account: plenty for one person's agents and scripts


def token_out(token: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        scope=token.scope,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        last_used_ip=token.last_used_ip,
        expired=token.expires_at is not None and token.expires_at <= utcnow(),
    )


class TokenService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    def _require_person(self) -> None:
        """Signed in to MoMaTo itself (not anonymous, not through a token)."""
        if self.principal.must_change_password:
            raise PasswordChangeRequiredError("set a new password first")
        if self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to manage API tokens")
        if self.principal.token_id is not None:
            raise PermissionDeniedError("API tokens are managed in MoMaTo, not through a token")

    def _listed(self, user_id: int) -> list[ApiTokenOut]:
        """Tokens not revoked (expired ones too, so they can be cleared away), newest first."""
        rows = self.session.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
            .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
        )
        return [token_out(t) for t in rows]

    def _revoke(self, token: ApiToken | None, user_id: int) -> None:
        if token is None or token.user_id != user_id or token.revoked_at is not None:
            raise NotFoundError("no such token")
        token.revoked_at = utcnow()
        audit.record(
            self.session,
            "token.revoked",
            actor_user_id=self.principal.user_id,
            target_type="user",
            target_id=user_id,
            token=token.name,
        )
        self.session.commit()

    # ------------------------------------------------------------------ your own

    def mine(self) -> list[ApiTokenOut]:
        self._require_person()
        return self._listed(self.principal.user_id)

    def create(self, data: ApiTokenCreate) -> ApiTokenCreated:
        self._require_person()
        user_id = self.principal.user_id
        live = self.session.scalars(
            select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        ).all()
        if sum(api_tokens.is_live(t) for t in live) >= MAX_LIVE_TOKENS:
            raise RuleViolationError(
                f"at most {MAX_LIVE_TOKENS} tokens at a time: revoke one you no longer use"
            )
        expires = None
        if data.expires_in_days is not None:
            expires = utcnow() + timedelta(days=data.expires_in_days)
        token, secret = api_tokens.issue(
            self.session, user_id, name=data.name, scope=data.scope, expires_at=expires
        )
        audit.record(
            self.session,
            "token.created",
            actor_user_id=user_id,
            target_type="user",
            target_id=user_id,
            token=token.name,
            scope=token.scope.value,
            expires_at=expires.isoformat() if expires else None,
        )
        self.session.commit()
        return ApiTokenCreated(token=token_out(token), secret=secret)

    def revoke(self, token_id: int) -> None:
        self._require_person()
        self._revoke(self.session.get(ApiToken, token_id), self.principal.user_id)

    # ------------------------------------------------------------------ anyone's (users.manage)

    def _require_admin(self, user_id: int) -> None:
        self._require_person()
        self.principal.require(Permission.USERS_MANAGE)
        if self.session.get(User, user_id) is None:
            raise NotFoundError(f"no person {user_id}")

    def of_user(self, user_id: int) -> list[ApiTokenOut]:
        self._require_admin(user_id)
        return self._listed(user_id)

    def revoke_of_user(self, user_id: int, token_id: int) -> None:
        self._require_admin(user_id)
        self._revoke(self.session.get(ApiToken, token_id), user_id)
