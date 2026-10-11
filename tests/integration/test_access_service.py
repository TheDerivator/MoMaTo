"""Access administration: assignments, default grants, status, the lockout guard. [AUTH-4]"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import AuditEntry, DefaultGrant, RoleAssignment, User, UserSession
from momato.db.models.people import UserStatus
from momato.domain.access import ADMIN_USERNAME, Audience, Scope
from momato.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from momato.identity import sessions
from momato.identity.lockout import active_administrators
from momato.identity.principal import principal_for_user
from momato.services.access import AccessService
from tests.factories import make_org, make_user


@pytest.fixture
def admin(session: Session) -> User:
    user = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert user is not None
    return user


@pytest.fixture
def service(session: Session, admin: User) -> AccessService:
    return AccessService(session, principal_for_user(session, admin))


def actions(session: Session) -> list[str]:
    return [a.action for a in session.scalars(select(AuditEntry).order_by(AuditEntry.id))]


def test_only_those_with_users_manage_may_administer_access(session: Session) -> None:
    anna = make_user(session, "Anna", make_org(session, "Org"))
    with pytest.raises(PermissionDeniedError, match=r"users\.manage"):
        AccessService(session, principal_for_user(session, anna))


def test_assigning_a_role_is_recorded_and_changes_what_the_person_may_do(
    session: Session, service: AccessService
) -> None:
    org = make_org(session, "Org")
    anna = make_user(session, "Anna", org)
    assignment = service.assign_role(anna.id, "project_admin", Scope.node(org.id))
    assert assignment.scope == Scope.node(org.id)
    principal = principal_for_user(session, anna)
    from momato.domain.access import Permission

    assert principal.can(Permission.PROJECT_EDIT, org.id)
    assert "user.role_granted" in actions(session)  # [AUTH-5] rights changes are audited


def test_assignments_are_validated(session: Session, service: AccessService) -> None:
    org = make_org(session, "Org")
    anna = make_user(session, "Anna", org)
    service.assign_role(anna.id, "viewer", Scope.everywhere())
    with pytest.raises(ConflictError, match="already holds"):
        service.assign_role(anna.id, "viewer", Scope.everywhere())
    with pytest.raises(NotFoundError, match="no role"):
        service.assign_role(anna.id, "no_such_role", Scope.everywhere())
    with pytest.raises(NotFoundError, match="no person"):
        service.assign_role(9999, "viewer", Scope.everywhere())
    with pytest.raises(RuleViolationError, match="no org node"):
        service.assign_role(anna.id, "viewer", Scope.node(9999))
    visitor = session.scalar(select(User).where(User.username == "anonymous"))
    assert visitor is not None
    with pytest.raises(RuleViolationError, match="anonymous visitor holds no roles"):
        service.assign_role(visitor.id, "viewer", Scope.everywhere())


def test_removing_an_assignment(session: Session, service: AccessService) -> None:
    org = make_org(session, "Org")
    anna = make_user(session, "Anna", org)
    assignment = service.assign_role(anna.id, "viewer", Scope.node(org.id))
    service.remove_assignment(assignment.id)
    assert session.get(RoleAssignment, assignment.id) is None
    assert "user.role_revoked" in actions(session)
    with pytest.raises(NotFoundError):
        service.remove_assignment(assignment.id)


# ---------------------------------------------------------------- the lockout guard


def test_the_last_administrator_cannot_lose_their_role(
    session: Session, service: AccessService, admin: User
) -> None:
    assert active_administrators(session) == 1
    mine = session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == admin.id))
    assert mine is not None
    with pytest.raises(RuleViolationError, match="at least one active administrator"):
        service.remove_assignment(mine.id)
    session.rollback()
    assert active_administrators(session) == 1


def test_the_role_can_go_when_another_administrator_remains(
    session: Session, service: AccessService, admin: User
) -> None:
    deputy = make_user(session, "Deputy", make_org(session, "Org"))
    service.assign_role(deputy.id, "admin", Scope.everywhere())
    assert active_administrators(session) == 2
    mine = session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == admin.id))
    assert mine is not None
    service.remove_assignment(mine.id)
    assert active_administrators(session) == 1


def test_an_administrator_on_one_branch_does_not_count(
    session: Session, service: AccessService, admin: User
) -> None:
    org = make_org(session, "Org")
    local = make_user(session, "Local", org)
    service.assign_role(local.id, "admin", Scope.node(org.id))
    assert active_administrators(session) == 1  # only the global one
    suspended = make_user(session, "Suspended", org)
    service.assign_role(suspended.id, "admin", Scope.everywhere())
    service.set_status(suspended.id, UserStatus.SUSPENDED)
    assert active_administrators(session) == 1  # a suspended one does not count


def test_an_administrator_may_be_suspended_while_another_remains(
    session: Session, service: AccessService
) -> None:
    deputy = make_user(session, "Deputy", make_org(session, "Org"))
    service.assign_role(deputy.id, "admin", Scope.everywhere())
    service.set_status(deputy.id, UserStatus.SUSPENDED)
    assert active_administrators(session) == 1
    service.set_status(deputy.id, UserStatus.ACTIVE)
    assert active_administrators(session) == 2


def test_nobody_may_suspend_the_only_administrator_not_even_someone_with_the_right(
    session: Session, service: AccessService, admin: User
) -> None:
    """Someone can hold users.manage through a default grant without being a counted
    administrator; suspending the one real administrator would still lock everyone out."""
    service.add_default_grant(Audience.SIGNED_IN, "admin", Scope.everywhere())
    clerk = make_user(session, "Clerk", make_org(session, "Org"))
    acting = AccessService(session, principal_for_user(session, clerk))
    with pytest.raises(RuleViolationError, match="at least one active administrator"):
        acting.set_status(admin.id, UserStatus.SUSPENDED)
    session.rollback()
    session.expire_all()
    assert admin.status is UserStatus.ACTIVE
    assert active_administrators(session) == 1


# ---------------------------------------------------------------- status


def test_a_suspended_person_loses_their_sessions_at_once(
    session: Session, service: AccessService
) -> None:
    anna = make_user(session, "Anna", make_org(session, "Org"), username="anna")
    token = sessions.start_session(session, anna, lifetime=timedelta(hours=1))
    session.flush()
    assert sessions.user_for_token(session, token) is not None

    service.set_status(anna.id, UserStatus.SUSPENDED)
    assert sessions.user_for_token(session, token) is None
    assert list(session.scalars(select(UserSession))) == []
    assert "user.status_changed" in actions(session)

    service.set_status(anna.id, UserStatus.ACTIVE)
    assert anna.status is UserStatus.ACTIVE


def test_status_rules(session: Session, service: AccessService, admin: User) -> None:
    visitor = session.scalar(select(User).where(User.username == "anonymous"))
    assert visitor is not None
    with pytest.raises(RuleViolationError, match="anonymous visitor cannot be suspended"):
        service.set_status(visitor.id, UserStatus.SUSPENDED)
    with pytest.raises(RuleViolationError, match="your own account"):
        service.set_status(admin.id, UserStatus.SUSPENDED)
    deputy = make_user(session, "Deputy", make_org(session, "Org"))
    service.assign_role(deputy.id, "admin", Scope.everywhere())
    as_deputy = AccessService(session, principal_for_user(session, deputy))
    with pytest.raises(RuleViolationError, match="built-in account cannot be deactivated"):
        as_deputy.set_status(admin.id, UserStatus.DEACTIVATED)
    with pytest.raises(NotFoundError):
        service.set_status(9999, UserStatus.ACTIVE)


def test_deactivating_a_person_keeps_them_but_ends_their_access(
    session: Session, service: AccessService
) -> None:
    anna = make_user(session, "Anna", make_org(session, "Org"))
    service.set_status(anna.id, UserStatus.DEACTIVATED)
    assert anna.status is UserStatus.DEACTIVATED
    assert session.get(User, anna.id) is not None  # never deleted (ADM-2)


# ---------------------------------------------------------------- default grants


def test_default_grants_can_be_changed_by_administrators(
    session: Session, service: AccessService
) -> None:
    existing = list(
        session.scalars(select(DefaultGrant).where(DefaultGrant.audience == Audience.SIGNED_IN))
    )
    assert len(existing) == 2
    for grant in existing:
        service.remove_default_grant(grant.id)
    assert list(session.scalars(select(DefaultGrant))) == []

    added = service.add_default_grant(Audience.ANONYMOUS, "viewer", Scope.everywhere())
    assert added.audience is Audience.ANONYMOUS
    with pytest.raises(ConflictError, match="exists already"):
        service.add_default_grant(Audience.ANONYMOUS, "viewer", Scope.everywhere())
    with pytest.raises(NotFoundError):
        service.remove_default_grant(9999)
    with pytest.raises(RuleViolationError, match="no org node"):
        service.add_default_grant(Audience.SIGNED_IN, "viewer", Scope.node(9999))
    assert {"access.default_revoked", "access.default_granted"} <= set(actions(session))
