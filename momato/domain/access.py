"""Access-control vocabulary and decisions: permissions, built-in roles, scopes, grants (§6).

Pure data and pure decisions. Loading a person's assignments and building query filters live in
`momato.identity`. Permissions are scoped to org-tree branches: a grant on a node covers its whole
subtree; a global permission counts only when granted globally.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from momato.domain.orgtree import OrgTree


class Permission(StrEnum):
    """Everything that can be granted. Scoped permissions apply per org node (its subtree)."""

    PROJECT_VIEW = "project.view"
    PROJECT_EDIT = "project.edit"
    PROJECT_COMMENT = "project.comment"
    PROJECT_DELETE = "project.delete"
    PLAN_MANAGE = "plan.manage"
    HOURS_VIEW = "hours.view"
    ORG_MANAGE = "org.manage"
    USERS_MANAGE = "users.manage"

    @property
    def is_scoped(self) -> bool:
        return self in SCOPED_PERMISSIONS


SCOPED_PERMISSIONS = frozenset(
    {
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_COMMENT,
        Permission.PROJECT_DELETE,
        Permission.PLAN_MANAGE,
        Permission.HOURS_VIEW,
    }
)

PERMISSION_DESCRIPTIONS: dict[Permission, str] = {
    Permission.PROJECT_VIEW: "See projects: all tabs, planned days, logged totals, plans",
    Permission.PROJECT_EDIT: (
        "Create projects; edit fields, details, tasks, planned days, members and plan links"
    ),
    Permission.PROJECT_COMMENT: "Post remarks, replies and images",
    Permission.PROJECT_DELETE: "Delete a project that has no booked time",
    Permission.PLAN_MANAGE: "Create, edit and delete action plans",
    Permission.HOURS_VIEW: "See the time booked by people (Spent, Compare, drill-downs, exports)",
    Permission.ORG_MANAGE: "Manage the org tree, departments, people, work patterns, availability",
    Permission.USERS_MANAGE: "Manage sign-in, roles, assignments, the audit log; delete any remark",
}


class BuiltinRole(StrEnum):
    """Roles that always exist. Their permissions are synced from code at every start."""

    VIEWER = "viewer"
    PROJECT_ADMIN = "project_admin"
    HOURS_VIEWER = "hours_viewer"
    ADMIN = "admin"

    @property
    def label(self) -> str:
        return BUILTIN_ROLE_LABELS[self]

    @property
    def permissions(self) -> frozenset[Permission]:
        return BUILTIN_ROLE_PERMISSIONS[self]


BUILTIN_ROLE_LABELS = {
    BuiltinRole.VIEWER: "Viewer",
    BuiltinRole.PROJECT_ADMIN: "Project administrator",
    BuiltinRole.HOURS_VIEWER: "Hours viewer",
    BuiltinRole.ADMIN: "Administrator",
}

BUILTIN_ROLE_PERMISSIONS: dict[BuiltinRole, frozenset[Permission]] = {
    BuiltinRole.VIEWER: frozenset({Permission.PROJECT_VIEW}),
    BuiltinRole.PROJECT_ADMIN: frozenset(
        {
            Permission.PROJECT_VIEW,
            Permission.PROJECT_EDIT,
            Permission.PROJECT_COMMENT,
            Permission.PLAN_MANAGE,
        }
    ),
    BuiltinRole.HOURS_VIEWER: frozenset({Permission.HOURS_VIEW}),
    BuiltinRole.ADMIN: frozenset(Permission),
}


class TokenScope(StrEnum):
    """What an API token (for AI agents and scripts) may do on behalf of its owner (TOK-1)."""

    READ = "read"
    WRITE = "write"

    @property
    def permissions(self) -> frozenset[Permission]:
        """The owner's permissions a token keeps; administration is never among them."""
        return TOKEN_PERMISSIONS[self]


TOKEN_NEVER = frozenset({Permission.ORG_MANAGE, Permission.USERS_MANAGE})
VIEW_PERMISSIONS = frozenset({Permission.PROJECT_VIEW, Permission.HOURS_VIEW})

TOKEN_PERMISSIONS: dict[TokenScope, frozenset[Permission]] = {
    TokenScope.READ: VIEW_PERMISSIONS,
    TokenScope.WRITE: frozenset(Permission) - TOKEN_NEVER,
}


class ScopeKind(StrEnum):
    GLOBAL = "global"
    NODE = "node"
    OWN_DEPARTMENT = "own_department"  # the department of the person holding the grant


@dataclass(frozen=True, slots=True)
class Scope:
    """Where an assignment applies: everywhere, one org node's branch, or own department."""

    kind: ScopeKind
    node_id: int | None = None

    def __post_init__(self) -> None:
        if (self.kind is ScopeKind.NODE) != (self.node_id is not None):
            raise ValueError("a node scope needs a node id; the other scopes have none")

    @property
    def key(self) -> str:
        """Stable text form (`global`, `node:3`, `own_department`), unique per assignment."""
        return f"node:{self.node_id}" if self.node_id is not None else self.kind.value

    @classmethod
    def everywhere(cls) -> Scope:
        return cls(ScopeKind.GLOBAL)

    @classmethod
    def node(cls, node_id: int) -> Scope:
        return cls(ScopeKind.NODE, node_id)

    @classmethod
    def own_department(cls) -> Scope:
        return cls(ScopeKind.OWN_DEPARTMENT)


class Audience(StrEnum):
    """Who a default grant holds for (D-013)."""

    SIGNED_IN = "signed_in"  # every signed-in person
    ANONYMOUS = "anonymous"  # every visitor, and a floor for everyone


ADMIN_USERNAME = "admin"
ANONYMOUS_USERNAME = "anonymous"

# What a fresh installation grants (D-013); administrators change both like any other assignment.
DEFAULT_GRANTS: dict[Audience, list[tuple[BuiltinRole, Scope]]] = {
    Audience.SIGNED_IN: [
        (BuiltinRole.VIEWER, Scope.everywhere()),
        (BuiltinRole.HOURS_VIEWER, Scope.own_department()),
    ],
    Audience.ANONYMOUS: [],
}


# ---------------------------------------------------------------- decisions


@dataclass(frozen=True, slots=True)
class Grant:
    """One permission at one scope (a role assignment expands into several grants)."""

    permission: Permission
    scope: Scope


@dataclass(frozen=True, slots=True)
class Reach:
    """Where a permission applies: everywhere, or the branches below `node_ids`."""

    everywhere: bool
    node_ids: frozenset[int] = frozenset()

    @property
    def nowhere(self) -> bool:
        return not self.everywhere and not self.node_ids


class GrantSet:
    """Everything a principal is allowed, and the decisions derived from it.

    The own-department scope is resolved when the set is built: `own_department` is the node of
    the holder's department (None: they have none, and such grants apply nowhere).
    """

    def __init__(self, grants: Iterable[Grant] = (), own_department: int | None = None) -> None:
        self._grants = frozenset(grants)
        self.own_department = own_department

    def __iter__(self) -> Iterator[Grant]:
        return iter(self._grants)

    def __len__(self) -> int:
        return len(self._grants)

    def _roots(self, permission: Permission) -> tuple[bool, frozenset[int]]:
        """Whether granted globally, and the nodes whose branches it is granted on."""
        everywhere = False
        nodes: set[int] = set()
        for grant in self._grants:
            if grant.permission is not permission:
                continue
            kind = grant.scope.kind
            if kind is ScopeKind.GLOBAL:
                everywhere = True
            elif not permission.is_scoped:
                continue  # unscoped permissions count only when granted globally
            elif kind is ScopeKind.NODE and grant.scope.node_id is not None:
                nodes.add(grant.scope.node_id)
            elif kind is ScopeKind.OWN_DEPARTMENT and self.own_department is not None:
                nodes.add(self.own_department)
        return everywhere, frozenset(nodes)

    def allows(self, permission: Permission, node_id: int | None, tree: OrgTree) -> bool:
        """Whether `permission` holds for an object at `node_id`.

        `node_id=None` asks "everywhere?", which only a global grant satisfies.
        """
        everywhere, roots = self._roots(permission)
        if everywhere:
            return True
        if node_id is None or not roots:
            return False
        return tree.is_within(node_id, roots)

    def allows_somewhere(self, permission: Permission, tree: OrgTree) -> bool:
        """For showing controls ("+ New project" needs edit rights in some branch)."""
        everywhere, roots = self._roots(permission)
        return everywhere or any(root in tree for root in roots)

    def reach(self, permission: Permission, tree: OrgTree) -> Reach:
        everywhere, roots = self._roots(permission)
        if everywhere:
            return Reach(everywhere=True)
        return Reach(everywhere=False, node_ids=frozenset(r for r in roots if r in tree))
