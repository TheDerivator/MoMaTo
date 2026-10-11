"""The principal: who is making a request and what they may do (loaded once per request).

Services receive a Principal and call `require(...)` before acting, and `reach(...)` or the
`AccessPolicy` filters to restrict lists. The anonymous visitor is a principal too: it holds the
default grants of the anonymous audience, which are a floor for everyone (§6 rule 3, D-013).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from momato.db.models import (
    DefaultGrant,
    ExternalIdentity,
    GroupRoleMapping,
    OrgNode,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from momato.db.models.people import UserKind
from momato.domain.access import (
    ANONYMOUS_USERNAME,
    Audience,
    Grant,
    GrantSet,
    Permission,
    Reach,
    Scope,
    ScopeKind,
    TokenScope,
)
from momato.domain.errors import (
    AuthenticationRequiredError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from momato.domain.orgtree import OrgNodeRef, OrgTree


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    username: str | None
    name: str
    job_title: str | None
    org_node_id: int | None
    is_anonymous: bool
    is_system: bool
    must_change_password: bool
    grants: GrantSet
    tree: OrgTree
    # Set when a trusted proxy identifies the person on every request (there is no logging out).
    ambient_provider: str | None = None
    # Set when the request carries an API token (TOK-1): the grants are already narrowed to it,
    # and a read token writes nothing at all.
    token_id: int | None = None
    token_name: str | None = None
    token_scope: TokenScope | None = None
    token_last_used_at: datetime | None = None

    @property
    def department_id(self) -> int | None:
        """The nearest flagged node from the person's own node up (D-006), if any."""
        return self.grants.own_department

    def token_allows(self, permission: Permission) -> bool:
        """Whether the API token of this request (if any) may use `permission` at all (TOK-1)."""
        return self.token_scope is None or permission in self.token_scope.permissions

    def can(self, permission: Permission, node_id: int | None = None) -> bool:
        """Whether `permission` holds at an object in the org tree (None: everywhere)."""
        if self.must_change_password:
            return False
        if node_id is not None and node_id not in self.tree:
            return False
        return self.grants.allows(permission, node_id, self.tree)

    def require(self, permission: Permission, node_id: int | None = None) -> None:
        """Raise unless allowed: 401 for visitors who should log in, 403 otherwise."""
        if self.must_change_password:
            raise PasswordChangeRequiredError("set a new password first")
        if self.can(permission, node_id):
            return
        if self.is_anonymous:
            raise AuthenticationRequiredError("log in to do this")
        raise PermissionDeniedError(f"missing permission {permission.value}")

    def reach(self, permission: Permission) -> Reach:
        """Where `permission` applies: everywhere, or the branches below some nodes."""
        if self.must_change_password:
            return Reach(everywhere=False)
        return self.grants.reach(permission, self.tree)

    def can_somewhere(self, permission: Permission) -> bool:
        return not self.must_change_password and self.grants.allows_somewhere(permission, self.tree)

    def covered_nodes(self, permission: Permission) -> frozenset[int] | None:
        """Every node the permission covers (branches expanded); None means all of them."""
        reach = self.reach(permission)
        if reach.everywhere:
            return None
        return self.tree.covered_by(reach.node_ids)


def load_tree(session: Session) -> OrgTree:
    rows = session.execute(select(OrgNode.id, OrgNode.parent_id, OrgNode.is_department))
    return OrgTree(OrgNodeRef(id_, parent, department) for id_, parent, department in rows)


def _scope(kind: ScopeKind, node_id: int | None) -> Scope:
    return Scope(kind, node_id)


def _known(permission: str) -> bool:
    return permission in {p.value for p in Permission}


def load_assignment_grants(session: Session, user_id: int) -> list[Grant]:
    rows = session.execute(
        select(RolePermission.permission, RoleAssignment.scope_kind, RoleAssignment.org_node_id)
        .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
        .where(RoleAssignment.user_id == user_id)
    )
    return [
        Grant(Permission(permission), _scope(kind, node_id))
        for permission, kind, node_id in rows
        if _known(permission)  # tolerate permissions removed from code but still in the database
    ]


def load_default_grants(session: Session, audience: Audience) -> list[Grant]:
    rows = session.execute(
        select(RolePermission.permission, DefaultGrant.scope_kind, DefaultGrant.org_node_id)
        .join(DefaultGrant, DefaultGrant.role_id == RolePermission.role_id)
        .where(DefaultGrant.audience == audience)
    )
    return [
        Grant(Permission(permission), _scope(kind, node_id))
        for permission, kind, node_id in rows
        if _known(permission)
    ]


def load_group_grants(session: Session, user_id: int) -> list[Grant]:
    """Grants from group → role mappings, for the groups the person's identities last reported."""
    reported = {
        (provider, group)
        for provider, groups in session.execute(
            select(ExternalIdentity.provider, ExternalIdentity.groups).where(
                ExternalIdentity.user_id == user_id
            )
        )
        for group in groups or []
    }
    if not reported:
        return []
    mappings = session.scalars(
        select(GroupRoleMapping)
        .options(selectinload(GroupRoleMapping.role).selectinload(Role.permissions))
        .where(GroupRoleMapping.provider.in_({provider for provider, _ in reported}))
    )
    return [
        Grant(Permission(rp.permission), mapping.scope)
        for mapping in mappings
        if (mapping.provider, mapping.group_name) in reported
        for rp in mapping.role.permissions
        if _known(rp.permission)
    ]


def principal_for_user(session: Session, user: User) -> Principal:
    """Own assignments, the default grants of every signed-in person, and the anonymous
    visitor's grants as a floor (signing in never shows less)."""
    tree = load_tree(session)
    is_anonymous = user.username == ANONYMOUS_USERNAME and user.kind is UserKind.SYSTEM
    grants = load_default_grants(session, Audience.ANONYMOUS)
    if not is_anonymous:
        grants += load_assignment_grants(session, user.id)
        grants += load_group_grants(session, user.id)
        grants += load_default_grants(session, Audience.SIGNED_IN)
    return Principal(
        user_id=user.id,
        username=user.username,
        name=user.name,
        job_title=user.job_title,
        org_node_id=user.org_node_id,
        is_anonymous=is_anonymous,
        is_system=user.kind is UserKind.SYSTEM,
        must_change_password=user.must_change_password,
        grants=GrantSet(grants, own_department=tree.department_of(user.org_node_id)),
        tree=tree,
    )


def anonymous_principal(session: Session) -> Principal:
    user = session.scalars(select(User).where(User.username == ANONYMOUS_USERNAME)).one()
    return principal_for_user(session, user)
