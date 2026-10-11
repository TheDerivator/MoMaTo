"""The lockout guard: at least one active administrator always remains (AUTH-4)."""

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from momato.db.models import RoleAssignment, RolePermission, User
from momato.db.models.people import UserStatus
from momato.domain.access import ANONYMOUS_USERNAME, Permission, ScopeKind
from momato.domain.errors import RuleViolationError


def active_administrators(session: Session) -> int:
    """Active accounts (not the anonymous visitor) holding `users.manage` globally by a role."""
    return (
        session.scalar(
            select(func.count(distinct(User.id)))
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(RolePermission, RolePermission.role_id == RoleAssignment.role_id)
            .where(
                User.status == UserStatus.ACTIVE,
                or_(User.username.is_(None), User.username != ANONYMOUS_USERNAME),
                RoleAssignment.scope_kind == ScopeKind.GLOBAL,
                RolePermission.permission == Permission.USERS_MANAGE.value,
            )
        )
        or 0
    )


def ensure_administrator_remains(session: Session) -> None:
    """Call after a change that could remove an administrator, before committing it."""
    session.flush()
    if active_administrators(session) == 0:
        raise RuleViolationError(
            "this would leave nobody able to manage users; keep at least one active administrator"
        )
