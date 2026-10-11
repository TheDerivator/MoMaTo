"""Built-in data: roles synced from code, the admin and anonymous accounts, default grants."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from momato.db.models import (
    AppState,
    DefaultGrant,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.domain.access import (
    ADMIN_USERNAME,
    ANONYMOUS_USERNAME,
    Audience,
    BuiltinRole,
    Permission,
    Scope,
    ScopeKind,
)
from momato.identity.passwords import verify_password
from momato.identity.principal import principal_for_user
from momato.services.people import active_people
from momato.services.seed import DEFAULT_GRANTS_MARKER, reset_admin, seed_builtins
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.factories import make_org, make_user


def test_the_built_in_roles_hold_exactly_the_permissions_of_the_code(session: Session) -> None:
    roles = {r.key: r for r in session.scalars(select(Role))}
    assert set(roles) == {r.value for r in BuiltinRole}
    for builtin in BuiltinRole:
        role = roles[builtin.value]
        assert role.is_builtin
        assert {rp.permission for rp in role.permissions} == {p.value for p in builtin.permissions}
        assert role.name == builtin.label


def test_the_admin_and_anonymous_accounts_exist_and_are_system_accounts(session: Session) -> None:
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    anonymous = session.scalar(select(User).where(User.username == ANONYMOUS_USERNAME))
    assert admin is not None
    assert anonymous is not None
    assert admin.kind is UserKind.SYSTEM
    assert anonymous.kind is UserKind.SYSTEM
    assert verify_password(admin.password_hash, TEST_ADMIN_PASSWORD)
    assert not admin.must_change_password  # its password was chosen, not generated
    assert anonymous.password_hash is None  # nobody signs in as the visitor
    assert principal_for_user(session, anonymous).is_anonymous


def test_default_grants_are_the_decision_d_013(session: Session) -> None:
    rows = session.execute(
        select(DefaultGrant.audience, Role.key, DefaultGrant.scope_kind, DefaultGrant.org_node_id)
        .join(Role, Role.id == DefaultGrant.role_id)
        .order_by(DefaultGrant.id)
    ).all()
    assert [tuple(r) for r in rows] == [
        (Audience.SIGNED_IN, "viewer", ScopeKind.GLOBAL, None),
        (Audience.SIGNED_IN, "hours_viewer", ScopeKind.OWN_DEPARTMENT, None),
    ]


def test_seeding_again_creates_nothing(session: Session) -> None:
    report = seed_builtins(session, initial_admin_password="another-password-here")
    assert report.created == []
    assert report.generated_admin_password is None
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert admin is not None
    assert verify_password(admin.password_hash, TEST_ADMIN_PASSWORD)  # the first one stands


def test_built_in_permissions_are_resynced_but_custom_roles_are_left_alone(
    session: Session,
) -> None:
    viewer = session.scalar(select(Role).where(Role.key == "viewer"))
    assert viewer is not None
    viewer.permissions.append(RolePermission(permission="project.delete"))  # tampered
    viewer.permissions.append(RolePermission(permission="no.such.permission"))
    custom = Role(key="custom", name="Custom", is_builtin=False)
    custom.permissions.append(RolePermission(permission="project.delete"))
    session.add(custom)
    session.flush()

    seed_builtins(session)
    session.expire_all()
    assert {rp.permission for rp in viewer.permissions} == {"project.view"}
    assert {rp.permission for rp in custom.permissions} == {"project.delete"}


def test_a_removed_default_grant_is_not_created_again(session: Session) -> None:
    for grant in session.scalars(select(DefaultGrant)):
        session.delete(grant)
    session.flush()
    assert session.get(AppState, DEFAULT_GRANTS_MARKER) is not None
    seed_builtins(session)
    assert list(session.scalars(select(DefaultGrant))) == []


def test_a_generated_admin_password_is_reported_and_must_be_changed(session: Session) -> None:
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert admin is not None
    session.execute(delete(RoleAssignment))
    session.delete(admin)
    session.flush()
    report = seed_builtins(session)  # no password given
    assert report.generated_admin_password
    new_admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert new_admin is not None
    assert new_admin.must_change_password
    assert verify_password(new_admin.password_hash, report.generated_admin_password)


def test_reset_admin_repairs_the_account(session: Session) -> None:
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert admin is not None
    admin.status = UserStatus.SUSPENDED
    admin.password_hash = None
    session.flush()

    password, generated = reset_admin(session, password="a-chosen-password")
    assert (password, generated) == ("a-chosen-password", False)
    session.expire_all()
    assert admin.status is UserStatus.ACTIVE
    assert not admin.must_change_password
    assert verify_password(admin.password_hash, "a-chosen-password")

    generated_password, was_generated = reset_admin(session)
    assert was_generated
    assert admin.must_change_password
    assert verify_password(admin.password_hash, generated_password)
    principal = principal_for_user(session, admin)
    assert principal.grants.allows(Permission.USERS_MANAGE, None, principal.tree)


def test_reset_admin_creates_a_missing_account_with_one_assignment(session: Session) -> None:
    session.execute(delete(RoleAssignment))
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    assert admin is not None
    session.delete(admin)
    session.flush()

    reset_admin(session, password="a-chosen-password")
    reset_admin(session, password="a-chosen-password")  # twice: still one assignment
    assignments = list(session.scalars(select(RoleAssignment)))
    assert len(assignments) == 1
    assert assignments[0].scope == Scope.everywhere()


def test_people_who_work_here_are_people_and_system_accounts_never(session: Session) -> None:
    """[D-057] A suspended sign-in still works here; only deactivation takes a person out."""
    org = make_org(session, "Org")
    anna = make_user(session, "Anna", org)
    bram = make_user(session, "Bram", org)
    bram.status = UserStatus.DEACTIVATED
    carl = make_user(session, "Carl", org)
    carl.status = UserStatus.SUSPENDED
    session.flush()
    assert [p.name for p in active_people(session)] == [anna.name, carl.name]
    names = {u.name for u in active_people(session)}
    assert "Administrator" not in names
    assert "Anonymous visitor" not in names
