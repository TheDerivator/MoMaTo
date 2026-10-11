"""Access administration: assignments, roles, default grants, account status, audit log (ADM-3 – 6).

Everything here needs `users.manage`, is recorded in the audit log, and goes through the lockout
guard: no change may leave the installation without an active administrator (AUTH-4). The
administration endpoints (`/api/admin`) are thin layers over this service.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from momato.db.models import (
    AuditEntry,
    DefaultGrant,
    GroupRoleMapping,
    OrgNode,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.domain.access import (
    ANONYMOUS_USERNAME,
    PERMISSION_DESCRIPTIONS,
    Audience,
    Permission,
    Scope,
    ScopeKind,
)
from momato.domain.errors import ConflictError, NotFoundError, RuleViolationError
from momato.identity import sessions
from momato.identity.lockout import ensure_administrator_remains
from momato.identity.principal import Principal
from momato.schemas.admin import (
    AuditEntryOut,
    DefaultGrantOut,
    GroupMappingOut,
    PermissionInfo,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from momato.services import audit


class AccessService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        principal.require(Permission.USERS_MANAGE)

    def _record(self, action: str, target_type: str, target_id: object, **details: object) -> None:
        audit.record(
            self.session,
            action,
            actor_user_id=self.principal.user_id,
            target_type=target_type,
            target_id=target_id,
            **details,
        )

    def _user(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise NotFoundError(f"no person {user_id}")
        return user

    def _role(self, key: str) -> Role:
        role = self.session.scalar(select(Role).where(Role.key == key))
        if role is None:
            raise NotFoundError(f"no role {key!r}")
        return role

    def _check_scope(self, scope: Scope) -> None:
        if scope.kind is ScopeKind.NODE and self.session.get(OrgNode, scope.node_id) is None:
            raise RuleViolationError(f"no org node {scope.node_id}")

    # ------------------------------------------------------------ assignments

    def assign_role(self, user_id: int, role_key: str, scope: Scope) -> RoleAssignment:
        user = self._user(user_id)
        if user.username == ANONYMOUS_USERNAME:
            raise RuleViolationError("the anonymous visitor holds no roles: change the defaults")
        self._check_scope(scope)
        role = self._role(role_key)
        existing = self.session.scalar(
            select(RoleAssignment.id).where(
                RoleAssignment.user_id == user.id,
                RoleAssignment.role_id == role.id,
                RoleAssignment.scope_key == scope.key,
            )
        )
        if existing is not None:
            raise ConflictError("this person already holds that role at that scope")
        assignment = RoleAssignment(user_id=user.id, role_id=role.id)
        assignment.scope = scope
        self.session.add(assignment)
        self.session.flush()
        self._record("user.role_granted", "user", user.id, role=role.key, scope=scope.key)
        self.session.commit()
        return assignment

    def remove_assignment(self, assignment_id: int) -> None:
        assignment = self.session.get(RoleAssignment, assignment_id)
        if assignment is None:
            raise NotFoundError(f"no assignment {assignment_id}")
        user_id, role_key, scope_key = assignment.user_id, assignment.role.key, assignment.scope_key
        self.session.delete(assignment)
        ensure_administrator_remains(self.session)
        self._record("user.role_revoked", "user", user_id, role=role_key, scope=scope_key)
        self.session.commit()

    # ------------------------------------------------------------ default grants (D-013)

    def add_default_grant(self, audience: Audience, role_key: str, scope: Scope) -> DefaultGrant:
        self._check_scope(scope)
        role = self._role(role_key)
        existing = self.session.scalar(
            select(DefaultGrant.id).where(
                DefaultGrant.audience == audience,
                DefaultGrant.role_id == role.id,
                DefaultGrant.scope_key == scope.key,
            )
        )
        if existing is not None:
            raise ConflictError("that default grant exists already")
        grant = DefaultGrant(audience=audience, role_id=role.id)
        grant.scope = scope
        self.session.add(grant)
        self.session.flush()
        self._record(
            "access.default_granted", "role", role.key, audience=audience.value, scope=scope.key
        )
        self.session.commit()
        return grant

    def remove_default_grant(self, grant_id: int) -> None:
        grant = self.session.get(DefaultGrant, grant_id)
        if grant is None:
            raise NotFoundError(f"no default grant {grant_id}")
        role_key, audience, scope_key = grant.role.key, grant.audience, grant.scope_key
        self.session.delete(grant)
        self.session.flush()
        self._record(
            "access.default_revoked", "role", role_key, audience=audience.value, scope=scope_key
        )
        self.session.commit()

    # ------------------------------------------------------------ status

    def set_status(self, user_id: int, status: UserStatus) -> User:
        """Suspend, deactivate or reactivate a person; their sessions end at once (AUTH-4)."""
        user = self._user(user_id)
        if user.username == ANONYMOUS_USERNAME:
            raise RuleViolationError(
                "the anonymous visitor cannot be suspended: remove its default grants instead"
            )
        if user.id == self.principal.user_id and status is not UserStatus.ACTIVE:
            raise RuleViolationError("you cannot suspend or deactivate your own account")
        if user.kind is UserKind.SYSTEM and status is UserStatus.DEACTIVATED:
            raise RuleViolationError("a built-in account cannot be deactivated")
        user.status = status
        if status is not UserStatus.ACTIVE:
            sessions.end_all_sessions(self.session, user.id)
        ensure_administrator_remains(self.session)
        self._record("user.status_changed", "user", user.id, status=status.value)
        self.session.commit()
        return user

    # ------------------------------------------------------------ roles (ADM-5)

    @staticmethod
    def permissions() -> list[PermissionInfo]:
        """The permission catalog with its descriptions (for editing roles)."""
        return [
            PermissionInfo(value=p, scoped=p.is_scoped, description=PERMISSION_DESCRIPTIONS[p])
            for p in Permission
        ]

    def _count(self, model: type[RoleAssignment] | type[DefaultGrant], role: Role) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(model).where(model.role_id == role.id)
            )
            or 0
        )

    def _role_out(self, role: Role) -> RoleOut:
        known = {p.value for p in Permission}
        return RoleOut(
            id=role.id,
            key=role.key,
            name=role.name,
            description=role.description,
            is_builtin=role.is_builtin,
            permissions=sorted(
                Permission(rp.permission) for rp in role.permissions if rp.permission in known
            ),
            assignment_count=self._count(RoleAssignment, role),
            default_grant_count=self._count(DefaultGrant, role),
        )

    def roles(self) -> list[RoleOut]:
        found = self.session.scalars(
            select(Role).order_by(Role.is_builtin.desc(), Role.name, Role.id)
        )
        return [self._role_out(r) for r in found]

    def _custom_role(self, role_id: int) -> Role:
        role = self.session.get(Role, role_id)
        if role is None:
            raise NotFoundError(f"no role {role_id}")
        if role.is_builtin:
            raise RuleViolationError("built-in roles are defined by the application")
        return role

    def create_role(self, data: RoleCreate) -> RoleOut:
        if self.session.scalar(select(Role.id).where(Role.key == data.key)) is not None:
            raise ConflictError(f"a role with key {data.key} exists")
        role = Role(key=data.key, name=data.name.strip(), description=data.description.strip())
        role.permissions = [
            RolePermission(permission=p.value) for p in sorted(set(data.permissions))
        ]
        self.session.add(role)
        self.session.flush()
        self._record(
            "role.created",
            "role",
            role.key,
            name=role.name,
            permissions=sorted(p.value for p in set(data.permissions)),
        )
        self.session.commit()
        return self._role_out(role)

    def update_role(self, role_id: int, data: RoleUpdate) -> RoleOut:
        role = self._custom_role(role_id)
        changes: dict[str, object] = {}
        if data.name is not None and data.name.strip() != role.name:
            role.name = changes["name"] = data.name.strip()
        if data.description is not None and data.description.strip() != role.description:
            role.description = changes["description"] = data.description.strip()
        if data.permissions is not None:
            wanted = sorted(set(data.permissions))
            role.permissions = [RolePermission(permission=p.value) for p in wanted]
            changes["permissions"] = [p.value for p in wanted]
        ensure_administrator_remains(self.session)
        if changes:
            self._record("role.updated", "role", role.key, **changes)
        self.session.commit()
        return self._role_out(role)

    def delete_role(self, role_id: int) -> None:
        role = self._custom_role(role_id)
        if self._count(RoleAssignment, role) or self._count(DefaultGrant, role):
            raise ConflictError("the role is still assigned or granted by default: remove those")
        self._record("role.deleted", "role", role.key, name=role.name)
        self.session.delete(role)
        self.session.commit()

    # ------------------------------------------------------------ default grants (ADM-5)

    def default_grants(self) -> list[DefaultGrantOut]:
        labels = scope_labels(self.session)
        rows = self.session.execute(
            select(DefaultGrant, Role)
            .join(Role, Role.id == DefaultGrant.role_id)
            .order_by(DefaultGrant.audience, Role.name, DefaultGrant.id)
        )
        return [
            DefaultGrantOut(
                id=grant.id,
                audience=grant.audience,
                role_key=role.key,
                role_name=role.name,
                scope_kind=grant.scope_kind,
                node_id=grant.org_node_id,
                scope_label=scope_label(grant.scope, labels),
            )
            for grant, role in rows
        ]

    # ------------------------------------------------------------ SSO group mappings (AUTH-3)

    def group_mappings(self) -> list[GroupMappingOut]:
        labels = scope_labels(self.session)
        rows = self.session.execute(
            select(GroupRoleMapping, Role)
            .join(Role, Role.id == GroupRoleMapping.role_id)
            .order_by(GroupRoleMapping.provider, GroupRoleMapping.group_name, GroupRoleMapping.id)
        )
        return [
            GroupMappingOut(
                id=mapping.id,
                provider=mapping.provider,
                group_name=mapping.group_name,
                role_key=role.key,
                role_name=role.name,
                scope_kind=mapping.scope_kind,
                node_id=mapping.org_node_id,
                scope_label=scope_label(mapping.scope, labels),
            )
            for mapping, role in rows
        ]

    def add_group_mapping(
        self, provider: str, group_name: str, role_key: str, scope: Scope
    ) -> GroupRoleMapping:
        """Everyone the provider reports in `group_name` holds the role while they are in it."""
        self._check_scope(scope)
        role = self._role(role_key)
        existing = self.session.scalar(
            select(GroupRoleMapping.id).where(
                GroupRoleMapping.provider == provider,
                GroupRoleMapping.group_name == group_name,
                GroupRoleMapping.role_id == role.id,
                GroupRoleMapping.scope_key == scope.key,
            )
        )
        if existing is not None:
            raise ConflictError("that mapping exists already")
        mapping = GroupRoleMapping(provider=provider, group_name=group_name, role_id=role.id)
        mapping.scope = scope
        self.session.add(mapping)
        self.session.flush()
        self._record(
            "access.group_mapped",
            "role",
            role.key,
            provider=provider,
            group=group_name,
            scope=scope.key,
        )
        self.session.commit()
        return mapping

    def remove_group_mapping(self, mapping_id: int) -> None:
        mapping = self.session.get(GroupRoleMapping, mapping_id)
        if mapping is None:
            raise NotFoundError(f"no group mapping {mapping_id}")
        role = self.session.get(Role, mapping.role_id)
        self.session.delete(mapping)
        self.session.flush()
        ensure_administrator_remains(self.session)
        self._record(
            "access.group_unmapped",
            "role",
            role.key if role else mapping.role_id,
            provider=mapping.provider,
            group=mapping.group_name,
        )
        self.session.commit()

    # ------------------------------------------------------------ audit log (AUTH-5, ADM-6)

    def audit_log(
        self,
        *,
        limit: int = 50,
        before_id: int | None = None,
        action: str | None = None,
        actor_id: int | None = None,
    ) -> list[AuditEntryOut]:
        """Newest first; page back with `before_id`. `action` matches a prefix such as `user.`."""
        query = (
            select(AuditEntry, User.name)
            .outerjoin(User, User.id == AuditEntry.actor_user_id)
            .order_by(AuditEntry.id.desc())
            .limit(min(max(limit, 1), 200))
        )
        if before_id is not None:
            query = query.where(AuditEntry.id < before_id)
        if action:
            query = query.where(AuditEntry.action.startswith(action, autoescape=True))
        if actor_id is not None:
            query = query.where(AuditEntry.actor_user_id == actor_id)
        return [
            AuditEntryOut(
                id=entry.id,
                at=entry.at,
                actor_id=entry.actor_user_id,
                actor=name,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                details=entry.details or {},
            )
            for entry, name in self.session.execute(query)
        ]


def scope_labels(session: Session) -> dict[int, str]:
    """Every org node's path from just below the root: "STL › Quality" (the root: its name)."""
    nodes = {n.id: n for n in session.scalars(select(OrgNode))}

    def path(node_id: int) -> str:
        names: list[str] = []
        current: int | None = node_id
        while current is not None and current in nodes:
            node = nodes[current]
            if node.parent_id is not None or not names:
                names.append(node.name)
            current = node.parent_id
        return " › ".join(reversed(names))

    return {node_id: path(node_id) for node_id in nodes}


def scope_label(scope: Scope, labels: dict[int, str]) -> str:
    """The words for a scope: Everywhere, Own department or the branch's path."""
    if scope.kind is ScopeKind.GLOBAL:
        return "Everywhere"
    if scope.kind is ScopeKind.OWN_DEPARTMENT:
        return "Own department"
    return labels.get(scope.node_id or 0, "?")
