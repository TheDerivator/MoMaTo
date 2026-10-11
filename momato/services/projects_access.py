"""Loading a project for a caller: invisible is 404, visible but not allowed is 403 (§6 rule 6)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import Project
from momato.domain.access import Permission
from momato.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.services.common import member_ids


class ProjectAccess:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        self.policy = AccessPolicy(principal)

    def visible(self, number: int) -> Project:
        """The project, or NotFound when it does not exist or the caller may not see it."""
        project = self.session.scalar(
            select(Project).where(
                Project.number == number, self.policy.project_filter(Permission.PROJECT_VIEW)
            )
        )
        if project is None:
            raise NotFoundError(f"no project {number}")
        return project

    def can(self, project: Project, permission: Permission) -> bool:
        members: set[int] = (
            set() if self.principal.is_anonymous else member_ids(self.session, project.id)
        )
        return self.policy.can_on_project(
            permission,
            node_id=project.org_node_id,
            coordinator_id=project.coordinator_id,
            member_ids=members,
        )

    def _require(self, number: int, permission: Permission) -> Project:
        project = self.visible(number)
        if self.can(project, permission):
            return project
        if self.principal.must_change_password:
            raise PasswordChangeRequiredError("set a new password first")
        if self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to do this")
        raise PermissionDeniedError(f"missing permission {permission.value}")

    def editable(self, number: int) -> Project:
        return self._require(number, Permission.PROJECT_EDIT)

    def commentable(self, number: int) -> Project:
        return self._require(number, Permission.PROJECT_COMMENT)

    def deletable(self, number: int) -> Project:
        return self._require(number, Permission.PROJECT_DELETE)
