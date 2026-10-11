"""Server-side search for pickers: projects and people, as the user types (SH-12, TS-8, PD-4)."""

from sqlalchemy import ColumnElement, Unicode, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from momato.db.models import OrgNode, Project, User
from momato.db.models.people import UserKind, UserStatus
from momato.db.text import contains_ci
from momato.domain.access import Permission
from momato.domain.projects import BOOKABLE_STATUSES
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.schemas.search import PersonHit, ProjectHit

LIMIT = 20


class SearchService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        self.policy = AccessPolicy(principal)

    def projects(self, q: str, *, bookable: bool = False, limit: int = LIMIT) -> list[ProjectHit]:
        """Visible projects whose number or name contains `q`, highest number first.

        `bookable` keeps those a person can book time on: In preparation or In progress (TS-8).
        """
        conditions: list[ColumnElement[bool]] = [
            self.policy.project_filter(Permission.PROJECT_VIEW)
        ]
        needle = q.strip().lstrip("#").strip()
        if needle:
            parts = [contains_ci(Project.name, needle)]
            if needle.isdigit():
                parts.append(sql_cast(Project.number, Unicode(20)).contains(needle))
            conditions.append(or_(*parts))
        if bookable:
            conditions.append(Project.status.in_(BOOKABLE_STATUSES))
        rows = self.session.execute(
            select(Project.number, Project.name, Project.status, OrgNode.name)
            .join(OrgNode, OrgNode.id == Project.org_node_id)
            .where(*conditions)
            .order_by(Project.number.desc())
            .limit(min(limit, 50))
        )
        return [
            ProjectHit(number=number, name=name, status=status, org_node_name=node)
            for number, name, status, node in rows
        ]

    def people(self, q: str, *, limit: int = LIMIT) -> list[PersonHit]:
        """Active persons by name or job title; system accounts never appear (D-012)."""
        conditions: list[ColumnElement[bool]] = [
            User.kind == UserKind.PERSON,
            User.status != UserStatus.DEACTIVATED,
        ]
        needle = q.strip()
        if needle:
            conditions.append(
                or_(
                    contains_ci(User.name, needle),
                    contains_ci(func.coalesce(User.job_title, ""), needle),
                )
            )
        rows = self.session.scalars(
            select(User).where(*conditions).order_by(User.name, User.id).limit(min(limit, 50))
        )
        return [
            PersonHit(
                id=u.id, name=u.name, job_title=u.job_title, org_node_id=u.org_node_id, hue=u.hue
            )
            for u in rows
        ]
