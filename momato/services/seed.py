"""Built-in data that must always exist: lock rows, built-in roles, the admin and anonymous
accounts, and the default grants.

`seed_builtins` is idempotent and runs at every startup. It creates what is missing and re-syncs
built-in role permissions from code, but never undoes an administrator's choices (the default
grants are created once, so removing one stays removed).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import (
    AppLock,
    AppState,
    DefaultGrant,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.db.session import LOCK_NAMES
from momato.domain.access import (
    ADMIN_USERNAME,
    ANONYMOUS_USERNAME,
    DEFAULT_GRANTS,
    BuiltinRole,
    Scope,
)
from momato.identity.passwords import generate_password, hash_password
from momato.services import audit

# The `app_state` row that says the default grants were created: they are created only once.
DEFAULT_GRANTS_MARKER = "default_grants_seeded"


@dataclass
class SeedReport:
    """What `seed_builtins` changed. A generated admin password must be shown to the operator."""

    created: list[str] = field(default_factory=list[str])
    generated_admin_password: str | None = None


def seed_builtins(session: Session, *, initial_admin_password: str | None = None) -> SeedReport:
    report = SeedReport()
    _ensure_locks(session, report)
    roles = _sync_builtin_roles(session, report)
    _ensure_anonymous(session, report)
    _ensure_admin(session, roles, initial_admin_password, report)
    _ensure_default_grants(session, roles, report)
    session.flush()
    return report


def reset_admin(session: Session, *, password: str | None = None) -> tuple[str, bool]:
    """Create or repair the built-in `admin`: active, Administrator everywhere, with `password`.

    Without a password one is generated and the account must change it at first login. Returns
    the password and whether it was generated. For `python -m momato create-admin` (AUTH-1).
    """
    seed_builtins(session)  # roles and anonymous exist
    admin = session.scalar(select(User).where(User.username == ADMIN_USERNAME))
    role = session.scalar(select(Role).where(Role.key == BuiltinRole.ADMIN.value))
    if role is None:  # seed_builtins just created it
        raise RuntimeError("the built-in Administrator role is missing")
    generated = password is None
    secret = password or generate_password()
    if admin is None:
        admin = User(username=ADMIN_USERNAME, name="Administrator", kind=UserKind.SYSTEM)
        session.add(admin)
        session.flush()
    admin.status = UserStatus.ACTIVE
    admin.password_hash = hash_password(secret)
    admin.must_change_password = generated
    holds = session.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.user_id == admin.id,
            RoleAssignment.role_id == role.id,
            RoleAssignment.scope_key == Scope.everywhere().key,
        )
    )
    if holds is None:
        assignment = RoleAssignment(user_id=admin.id, role_id=role.id)
        assignment.scope = Scope.everywhere()
        session.add(assignment)
    audit.record(
        session, "user.admin_reset", actor_user_id=None, target_type="user", target_id=admin.id
    )
    session.flush()
    return secret, generated


def _ensure_locks(session: Session, report: SeedReport) -> None:
    existing = set(session.scalars(select(AppLock.name)))
    for name in LOCK_NAMES:
        if name not in existing:
            session.add(AppLock(name=name, counter=0))
            report.created.append(f"lock {name}")


def _sync_builtin_roles(session: Session, report: SeedReport) -> dict[BuiltinRole, Role]:
    roles: dict[BuiltinRole, Role] = {}
    for builtin in BuiltinRole:
        role = session.scalar(select(Role).where(Role.key == builtin.value))
        if role is None:
            role = Role(key=builtin.value, name=builtin.label, is_builtin=True)
            session.add(role)
            report.created.append(f"role {builtin.value}")
        wanted = {p.value for p in builtin.permissions}
        role.permissions = [rp for rp in role.permissions if rp.permission in wanted]
        have = {rp.permission for rp in role.permissions}
        role.permissions.extend(RolePermission(permission=p) for p in sorted(wanted - have))
        role.name = builtin.label
        roles[builtin] = role
    session.flush()
    return roles


def _ensure_anonymous(session: Session, report: SeedReport) -> None:
    if session.scalar(select(User.id).where(User.username == ANONYMOUS_USERNAME)):
        return
    user = User(
        username=ANONYMOUS_USERNAME,
        name="Anonymous visitor",
        kind=UserKind.SYSTEM,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    audit.record(session, "user.created", actor_user_id=None, target_type="user", target_id=user.id)
    report.created.append("user anonymous")


def _ensure_admin(
    session: Session,
    roles: dict[BuiltinRole, Role],
    initial_password: str | None,
    report: SeedReport,
) -> None:
    if session.scalar(select(User.id).where(User.username == ADMIN_USERNAME)):
        return
    password = initial_password or generate_password()
    user = User(
        username=ADMIN_USERNAME,
        name="Administrator",
        kind=UserKind.SYSTEM,
        password_hash=hash_password(password),
        must_change_password=initial_password is None,
    )
    session.add(user)
    session.flush()
    assignment = RoleAssignment(user_id=user.id, role_id=roles[BuiltinRole.ADMIN].id)
    assignment.scope = Scope.everywhere()
    session.add(assignment)
    audit.record(session, "user.created", actor_user_id=None, target_type="user", target_id=user.id)
    report.created.append("user admin")
    if initial_password is None:
        report.generated_admin_password = password


def _ensure_default_grants(
    session: Session, roles: dict[BuiltinRole, Role], report: SeedReport
) -> None:
    if session.get(AppState, DEFAULT_GRANTS_MARKER) is not None:
        return
    for audience, grants in DEFAULT_GRANTS.items():
        for builtin, scope in grants:
            grant = DefaultGrant(audience=audience, role_id=roles[builtin].id)
            grant.scope = scope
            session.add(grant)
            report.created.append(f"default grant {audience.value}: {builtin.value} {scope.key}")
    session.add(AppState(key=DEFAULT_GRANTS_MARKER, value="1"))
