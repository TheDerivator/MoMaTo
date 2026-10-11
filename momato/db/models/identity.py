"""Access control: roles, assignments, default grants, sessions, login attempts, the audit log."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from momato.db.base import Base, ShortText, Text, UTCDateTime, str_enum, utcnow
from momato.domain.access import Audience, Scope, ScopeKind, TokenScope


class Role(Base):
    """A named bundle of permissions. Built-in roles are synced from code (domain/access.py)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(50), unique=True)
    name: Mapped[str] = mapped_column(ShortText)
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(default=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(Unicode(50), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")


class _Scoped:
    """Columns and helpers of a role at a scope: global, one org node, or the holder's department.

    `scope_key` repeats the scope as text ("node:7") so uniqueness works the same on every
    backend (NULLs in unique constraints behave differently on SQLite and MS SQL).
    """

    scope_kind: Mapped[ScopeKind] = mapped_column(str_enum(ScopeKind, 20))
    org_node_id: Mapped[int | None] = mapped_column(ForeignKey("org_nodes.id"))
    scope_key: Mapped[str] = mapped_column(Unicode(40))

    @property
    def scope(self) -> Scope:
        return Scope(self.scope_kind, self.org_node_id)

    @scope.setter
    def scope(self, scope: Scope) -> None:
        self.scope_kind = scope.kind
        self.org_node_id = scope.node_id
        self.scope_key = scope.key


_SCOPE_CHECK = (
    "(scope_kind = 'node' AND org_node_id IS NOT NULL)"
    " OR (scope_kind <> 'node' AND org_node_id IS NULL)"
)


class RoleAssignment(Base, _Scoped):
    """Gives a person a role at a scope (ADM-5)."""

    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_key"),
        CheckConstraint(_SCOPE_CHECK, name="scope_matches_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)

    role: Mapped[Role] = relationship()


class DefaultGrant(Base, _Scoped):
    """A role every signed-in person holds, or every visitor (a floor for everyone; D-013)."""

    __tablename__ = "default_grants"
    __table_args__ = (
        UniqueConstraint("audience", "role_id", "scope_key"),
        CheckConstraint(_SCOPE_CHECK, name="scope_matches_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    audience: Mapped[Audience] = mapped_column(str_enum(Audience, 20))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)

    role: Mapped[Role] = relationship()


class ExternalIdentity(Base):
    """Links an identity at an external provider (e.g. Entra ID `sub`) to a person (AUTH-3)."""

    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    subject: Mapped[str] = mapped_column(Unicode(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # The provider's groups at the last sign-in; group mappings grant roles from these.
    groups: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")


class GroupRoleMapping(Base, _Scoped):
    """Everyone in an identity-provider group holds a role at a scope while they are in it."""

    __tablename__ = "group_role_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "group_name", "role_id", "scope_key"),
        CheckConstraint(_SCOPE_CHECK, name="scope_matches_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    group_name: Mapped[str] = mapped_column(Unicode(255))  # as the provider sends it
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)

    role: Mapped[Role] = relationship()


class SsoRequest(Base):
    """A sign-in in progress at an external provider (state, nonce, PKCE verifier); single use."""

    __tablename__ = "sso_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    nonce: Mapped[str] = mapped_column(Unicode(100))
    code_verifier: Mapped[str] = mapped_column(Unicode(128))
    return_to: Mapped[str] = mapped_column(Unicode(1000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class UserSession(Base):
    """A server-side login session. The cookie holds a random token; only its hash is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ip_address: Mapped[str | None] = mapped_column(Unicode(45))
    user_agent: Mapped[str | None] = mapped_column(Unicode(300))


class ApiToken(Base):
    """A personal API token for an AI agent or a script, acting as its owner (TOK-1). Only the
    hash is stored. Revoked tokens stay, so what was done through them keeps its name (TOK-3)."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(ShortText)  # "Claude Code on my laptop"
    token_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    prefix: Mapped[str] = mapped_column(Unicode(16))  # the token's start, to recognize it
    scope: Mapped[TokenScope] = mapped_column(str_enum(TokenScope))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # None: never
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_ip: Mapped[str | None] = mapped_column(Unicode(45))
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditEntry(Base):
    """Security-relevant actions: sign-ins, account and rights changes (AUTH-5)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Unicode(60))
    target_type: Mapped[str | None] = mapped_column(Unicode(40))
    target_id: Mapped[str | None] = mapped_column(Unicode(60))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LoginAttempt(Base):
    """Password login attempts, for throttling guessing (per account and per client address)."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(ShortText, index=True)
    ip_address: Mapped[str | None] = mapped_column(Unicode(45), index=True)
    success: Mapped[bool]
