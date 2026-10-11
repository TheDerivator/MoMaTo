"""The org tree editor (ADM-1): add, rename, move, reorder, flag a department, delete (org.manage).

The tree stays one tree: exactly one root, no cycles, sibling names unique. A node is deleted only
when nothing refers to it any more (branches, people, projects, plans, rights).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from momato.db.models import ActionPlan, DefaultGrant, OrgNode, Project, RoleAssignment, User
from momato.domain.access import Permission
from momato.domain.errors import ConflictError, NotFoundError, RuleViolationError
from momato.identity.principal import Principal, load_tree
from momato.schemas.admin import OrgNodeCreate, OrgNodeUpdate
from momato.schemas.reference import OrgNodeOut
from momato.services import audit


class OrgAdminService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        principal.require(Permission.ORG_MANAGE)

    # ------------------------------------------------------------ helpers

    def _record(self, action: str, node: OrgNode, **details: object) -> None:
        audit.record(
            self.session,
            action,
            actor_user_id=self.principal.user_id,
            target_type="org_node",
            target_id=node.id,
            branch=node.name,
            **details,
        )

    def _node(self, node_id: int) -> OrgNode:
        node = self.session.get(OrgNode, node_id)
        if node is None:
            raise NotFoundError(f"no org node {node_id}")
        return node

    def _siblings(self, parent_id: int | None) -> list[OrgNode]:
        """The children of a node in their order (for the root: just the root)."""
        return list(
            self.session.scalars(
                select(OrgNode)
                .where(OrgNode.parent_id == parent_id)
                .order_by(OrgNode.position, OrgNode.id)
            )
        )

    def _check_name(self, parent_id: int | None, name: str, own_id: int | None = None) -> None:
        clash = self.session.scalar(
            select(OrgNode.id).where(OrgNode.parent_id == parent_id, OrgNode.name == name)
        )
        if clash is not None and clash != own_id:
            raise ConflictError(f"this branch already has a node named {name!r}")

    def _count(self, *where: object) -> int:
        return self.session.scalar(select(func.count()).where(*where)) or 0  # type: ignore[arg-type]

    @staticmethod
    def _number(nodes: list[OrgNode]) -> None:
        for index, node in enumerate(nodes):
            node.position = index

    # ------------------------------------------------------------ reading

    def nodes(self) -> list[OrgNodeOut]:
        rows = self.session.scalars(
            select(OrgNode).order_by(OrgNode.parent_id, OrgNode.position, OrgNode.id)
        )
        return [OrgNodeOut.model_validate(n, from_attributes=True) for n in rows]

    # ------------------------------------------------------------ changes

    def create(self, data: OrgNodeCreate) -> OrgNode:
        parent = self._node(data.parent_id)
        self._check_name(parent.id, data.name)
        node = OrgNode(
            parent_id=parent.id,
            name=data.name,
            is_department=data.is_department,
            position=len(self._siblings(parent.id)),
        )
        self.session.add(node)
        self.session.flush()
        self._record("org.node_created", node, parent=parent.name, department=data.is_department)
        self.session.commit()
        return node

    def update(self, node_id: int, data: OrgNodeUpdate) -> OrgNode:
        node = self._node(node_id)
        changes: dict[str, object] = {}

        new_parent = node.parent_id
        if data.parent_id is not None and data.parent_id != node.parent_id:
            if node.parent_id is None:
                raise RuleViolationError("the root of the organisation cannot be moved")
            parent = self._node(data.parent_id)
            if node.id in load_tree(self.session).ancestors_or_self(parent.id):
                raise RuleViolationError("a branch cannot be moved into itself")
            new_parent = parent.id
            changes["moved_under"] = parent.name

        name = data.name.strip() if data.name is not None else node.name
        if name != node.name or new_parent != node.parent_id:
            self._check_name(new_parent, name, node.id)
        if name != node.name:
            changes["renamed_from"] = node.name
            node.name = name

        if data.is_department is not None and data.is_department != node.is_department:
            node.is_department = data.is_department
            changes["department"] = data.is_department

        if new_parent != node.parent_id or data.position is not None:
            if node.parent_id is None:
                raise RuleViolationError("the root of the organisation has no place among others")
            old_parent = node.parent_id
            node.parent_id = new_parent
            self.session.flush()
            others = [n for n in self._siblings(new_parent) if n.id != node.id]
            index = len(others) if data.position is None else min(data.position, len(others))
            others.insert(index, node)
            self._number(others)
            if new_parent != old_parent:
                self._number(self._siblings(old_parent))
            changes["position"] = index

        if changes:
            self._record("org.node_updated", node, **changes)
        self.session.commit()
        return node

    def delete(self, node_id: int) -> None:
        node = self._node(node_id)
        if node.parent_id is None:
            raise RuleViolationError("the root of the organisation cannot be deleted")
        usage = {
            "branches below it": self._count(OrgNode.parent_id == node.id),
            "people": self._count(User.org_node_id == node.id),
            "projects": self._count(Project.org_node_id == node.id),
            "action plans": self._count(ActionPlan.owner_org_node_id == node.id),
            "role assignments": self._count(RoleAssignment.org_node_id == node.id),
            "default grants": self._count(DefaultGrant.org_node_id == node.id),
        }
        blocking = [f"{count} {what}" for what, count in usage.items() if count]
        if blocking:
            raise ConflictError(f"{node.name} is still used by {', '.join(blocking)}")
        parent_id = node.parent_id
        self._record("org.node_deleted", node)
        self.session.delete(node)
        self.session.flush()
        self._number(self._siblings(parent_id))
        self.session.commit()
