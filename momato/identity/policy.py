"""The one access policy: answers `can(...)` for objects and builds the query filters (§6 rule 7).

Routers never decide access. Services ask this object, so a list, a count, an export and a single
object are always judged by the same rules: scoped permissions by the object's org node, plus the
implicit rights of a project's coordinator and members (D-014), plus everyone's own time.
"""

from collections.abc import Collection

from sqlalchemy import ColumnElement, false, or_, select, true

from momato.db.ids import in_ids
from momato.db.models import Project, ProjectMember, User
from momato.domain.access import Permission
from momato.identity.principal import Principal

# What a project's coordinator and its members may do whatever their assignments say (D-014).
COORDINATOR_PERMISSIONS = frozenset(
    {Permission.PROJECT_VIEW, Permission.PROJECT_EDIT, Permission.PROJECT_COMMENT}
)
MEMBER_PERMISSIONS = frozenset({Permission.PROJECT_VIEW, Permission.PROJECT_COMMENT})


class AccessPolicy:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    # ------------------------------------------------------------ decisions about one object

    def can_on_project(
        self,
        permission: Permission,
        *,
        node_id: int,
        coordinator_id: int | None,
        member_ids: Collection[int] = (),
    ) -> bool:
        """`permission` on a project at `node_id` with this coordinator and members."""
        principal = self.principal
        if principal.must_change_password:
            return False
        if not principal.is_anonymous and principal.token_allows(permission):
            # A token never holds more than its scope, whatever the owner's implicit rights are.
            if permission in COORDINATOR_PERMISSIONS and principal.user_id == coordinator_id:
                return True
            if permission in MEMBER_PERMISSIONS and principal.user_id in member_ids:
                return True
        return principal.can(permission, node_id)

    def can_see_hours_of(self, person_id: int, person_node_id: int | None) -> bool:
        """Everyone sees their own time; others' only with hours.view on the person's node."""
        principal = self.principal
        if principal.must_change_password:
            return False
        if not principal.is_anonymous and principal.user_id == person_id:
            return True
        if person_node_id is None:
            return principal.can(Permission.HOURS_VIEW)  # people without a node: global grants
        return principal.can(Permission.HOURS_VIEW, person_node_id)

    # ------------------------------------------------------------ query filters

    def project_filter(
        self, permission: Permission = Permission.PROJECT_VIEW
    ) -> ColumnElement[bool]:
        """A WHERE clause for `Project`: the projects `permission` holds for."""
        principal = self.principal
        nodes = principal.covered_nodes(permission)
        if nodes is None:
            return true()
        parts: list[ColumnElement[bool]] = []
        if nodes:
            parts.append(in_ids(Project.org_node_id, nodes))
        implicit = (
            not principal.is_anonymous
            and not principal.must_change_password
            and principal.token_allows(permission)
        )
        if implicit:
            if permission in COORDINATOR_PERMISSIONS:
                parts.append(Project.coordinator_id == principal.user_id)
            if permission in MEMBER_PERMISSIONS:
                parts.append(
                    Project.id.in_(
                        select(ProjectMember.project_id).where(
                            ProjectMember.user_id == principal.user_id
                        )
                    )
                )
        return or_(*parts) if parts else false()

    def people_hours_filter(self) -> ColumnElement[bool]:
        """A WHERE clause for `User`: the people whose booked time the caller may see."""
        principal = self.principal
        if principal.must_change_password:
            return false()
        nodes = principal.covered_nodes(Permission.HOURS_VIEW)
        if nodes is None:
            return true()
        parts: list[ColumnElement[bool]] = []
        if nodes:
            parts.append(in_ids(User.org_node_id, nodes))
        if not principal.is_anonymous:
            parts.append(User.id == principal.user_id)
        return or_(*parts) if parts else false()
