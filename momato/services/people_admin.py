"""People administration: data and availability (`org.manage`), sign-in and rights (`users.manage`).

One person record is both the person and their account (D-012). People are never deleted:
deactivating one keeps their history and takes them out of pickers and planning (ADM-2). The
second half, sign-in and rights, needs `users.manage` and, like everything here, is recorded in
the audit log.
"""

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from momato.db.ids import in_ids
from momato.db.models import (
    Availability,
    ExternalIdentity,
    OrgNode,
    Role,
    RoleAssignment,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.db.text import contains_ci
from momato.domain.access import Permission
from momato.domain.capacity import WorkPattern, year_availability_days
from momato.domain.errors import ConflictError, NotFoundError, RuleViolationError
from momato.domain.fields import Profile
from momato.identity import sessions
from momato.identity.lockout import ensure_administrator_remains
from momato.identity.passwords import generate_password, hash_password, password_problems
from momato.identity.principal import Principal
from momato.schemas.admin import (
    AssignmentIn,
    AssignmentOut,
    AvailabilityOut,
    ExternalIdentityOut,
    PasswordReset,
    PasswordResetOut,
    PersonAdminOut,
    PersonCreate,
    PersonUpdate,
    SignInUpdate,
)
from momato.services import audit
from momato.services.access import AccessService, scope_label, scope_labels

USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}")


def work_pattern(user: User) -> WorkPattern:
    return WorkPattern(
        (
            user.work_minutes_mon,
            user.work_minutes_tue,
            user.work_minutes_wed,
            user.work_minutes_thu,
            user.work_minutes_fri,
        )
    )


def availability_rows(
    user: User, overrides: dict[int, Decimal], profile: Profile, today: date
) -> list[AvailabilityOut]:
    """This year, next year and every year with an override, each with the default it replaces."""
    default = float(
        year_availability_days(None, work_pattern(user), profile.numbers.available_days_per_year)
    )
    years = sorted({today.year, today.year + 1} | set(overrides))
    return [
        AvailabilityOut(
            year=year,
            override_days=float(overrides[year]) if year in overrides else None,
            default_days=default,
            days=float(overrides[year]) if year in overrides else default,
        )
        for year in years
    ]


class PeopleAdminService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        self.manages_users = principal.can(Permission.USERS_MANAGE)
        if not (principal.can(Permission.ORG_MANAGE) or self.manages_users):
            principal.require(Permission.ORG_MANAGE)  # raises the right 401 or 403

    # ------------------------------------------------------------ helpers

    def _record(self, action: str, user: User, **details: object) -> None:
        audit.record(
            self.session,
            action,
            actor_user_id=self.principal.user_id,
            target_type="user",
            target_id=user.id,
            person=user.name,
            **details,
        )

    def _person(self, person_id: int) -> User:
        user = self.session.get(User, person_id)
        if user is None or user.kind is not UserKind.PERSON:
            raise NotFoundError(f"no person {person_id}")
        return user

    def _node(self, node_id: int) -> OrgNode:
        node = self.session.get(OrgNode, node_id)
        if node is None:
            raise RuleViolationError(f"no org node {node_id}")
        return node

    def _need_org(self) -> None:
        self.principal.require(Permission.ORG_MANAGE)

    def _need_users(self) -> None:
        self.principal.require(Permission.USERS_MANAGE)

    # ------------------------------------------------------------ reading

    def _out(self, users: list[User]) -> list[PersonAdminOut]:
        """Two bulk queries (overrides, assignments), not two per person."""
        ids = [u.id for u in users]
        overrides: dict[int, dict[int, Decimal]] = {}
        assignments: dict[int, list[AssignmentOut]] = {}
        if ids:
            for row in self.session.scalars(
                select(Availability).where(in_ids(Availability.user_id, ids))
            ):
                overrides.setdefault(row.user_id, {})[row.year] = row.days
        if ids and self.manages_users:
            labels = scope_labels(self.session)
            rows = self.session.execute(
                select(RoleAssignment, Role)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(in_ids(RoleAssignment.user_id, ids))
                .order_by(RoleAssignment.id)
            )
            for assignment, role in rows:
                assignments.setdefault(assignment.user_id, []).append(
                    AssignmentOut(
                        id=assignment.id,
                        role_key=role.key,
                        role_name=role.name,
                        scope_kind=assignment.scope_kind,
                        node_id=assignment.org_node_id,
                        scope_label=scope_label(assignment.scope, labels),
                    )
                )
        identities: dict[int, list[ExternalIdentityOut]] = {}
        if ids and self.manages_users:
            for link in self.session.scalars(
                select(ExternalIdentity)
                .where(in_ids(ExternalIdentity.user_id, ids))
                .order_by(ExternalIdentity.id)
            ):
                identities.setdefault(link.user_id, []).append(
                    ExternalIdentityOut(
                        provider=link.provider,
                        last_seen_at=link.last_seen_at,
                        groups=list(link.groups or []),
                    )
                )
        users_only = self.manages_users
        return [
            PersonAdminOut(
                id=user.id,
                name=user.name,
                job_title=user.job_title,
                org_node_id=user.org_node_id,
                hue=user.hue,
                work_minutes=list(work_pattern(user).minutes),
                status=user.status,
                created_at=user.created_at,
                availability=availability_rows(
                    user, overrides.get(user.id, {}), self.profile, self.today
                ),
                username=user.username if users_only else None,
                email=user.email if users_only else None,
                has_password=bool(user.password_hash) and users_only,
                must_change_password=user.must_change_password and users_only,
                last_login_at=user.last_login_at if users_only else None,
                assignments=assignments.get(user.id, []),
                identities=identities.get(user.id, []),
            )
            for user in users
        ]

    def people(self, *, q: str | None = None) -> list[PersonAdminOut]:
        """Everyone (deactivated people too) by name; `q` matches name, username and email."""
        query = select(User).where(User.kind == UserKind.PERSON).order_by(User.name, User.id)
        needle = (q or "").strip()
        if needle:
            conditions = [contains_ci(User.name, needle)]
            if self.manages_users:
                conditions.append(contains_ci(func.coalesce(User.username, ""), needle))
                conditions.append(contains_ci(func.coalesce(User.email, ""), needle))
            query = query.where(or_(*conditions))
        return self._out(list(self.session.scalars(query)))

    def get(self, person_id: int) -> PersonAdminOut:
        return self._out([self._person(person_id)])[0]

    # ------------------------------------------------------------ data (org.manage)

    @staticmethod
    def _set_pattern(user: User, minutes: list[int]) -> None:
        (
            user.work_minutes_mon,
            user.work_minutes_tue,
            user.work_minutes_wed,
            user.work_minutes_thu,
            user.work_minutes_fri,
        ) = minutes

    def create(self, data: PersonCreate) -> PersonAdminOut:
        self._need_org()
        self._node(data.org_node_id)
        user = User(
            kind=UserKind.PERSON,
            name=data.name.strip(),
            job_title=(data.job_title or "").strip() or None,
            org_node_id=data.org_node_id,
            hue=data.hue,
        )
        if data.work_minutes is not None:
            self._set_pattern(user, data.work_minutes)
        self.session.add(user)
        self.session.flush()
        self._record("person.created", user, org_node_id=user.org_node_id)
        self.session.commit()
        return self.get(user.id)

    def update(self, person_id: int, data: PersonUpdate) -> PersonAdminOut:
        self._need_org()
        user = self._person(person_id)
        changes: dict[str, object] = {}
        if data.name is not None and data.name.strip() != user.name:
            user.name = changes["name"] = data.name.strip()
        if "job_title" in data.model_fields_set:
            title = (data.job_title or "").strip() or None
            if title != user.job_title:
                user.job_title = changes["job_title"] = title
        if data.org_node_id is not None and data.org_node_id != user.org_node_id:
            self._node(data.org_node_id)
            user.org_node_id = changes["org_node_id"] = data.org_node_id
        if data.hue is not None and data.hue != user.hue:
            user.hue = changes["hue"] = data.hue
        if data.work_minutes is not None and data.work_minutes != list(work_pattern(user).minutes):
            self._set_pattern(user, data.work_minutes)
            changes["work_minutes"] = data.work_minutes
        if changes:
            self._record("person.updated", user, **changes)
        self.session.commit()
        return self.get(user.id)

    def set_availability(self, person_id: int, year: int, days: Decimal) -> PersonAdminOut:
        self._need_org()
        user = self._person(person_id)
        row = self.session.get(Availability, (user.id, year))
        if row is None:
            self.session.add(Availability(user_id=user.id, year=year, days=days))
        else:
            row.days = days
        self._record("person.availability_set", user, year=year, days=str(days))
        self.session.commit()
        return self.get(user.id)

    def clear_availability(self, person_id: int, year: int) -> PersonAdminOut:
        self._need_org()
        user = self._person(person_id)
        row = self.session.get(Availability, (user.id, year))
        if row is not None:
            self.session.delete(row)
            self._record("person.availability_cleared", user, year=year)
        self.session.commit()
        return self.get(user.id)

    def _change_status(self, user: User, status: UserStatus) -> None:
        if user.id == self.principal.user_id and status is UserStatus.DEACTIVATED:
            raise RuleViolationError("you cannot deactivate your own account")
        user.status = status
        if status is UserStatus.DEACTIVATED:
            sessions.end_all_sessions(self.session, user.id)
        ensure_administrator_remains(self.session)
        self._record("user.status_changed", user, status=status.value)
        self.session.commit()

    def deactivate(self, person_id: int) -> PersonAdminOut:
        """The person has left: no sign-in, out of pickers and planning, history kept."""
        self._need_org()
        user = self._person(person_id)
        if user.status is UserStatus.DEACTIVATED:
            raise ConflictError(f"{user.name} is deactivated already")
        self._change_status(user, UserStatus.DEACTIVATED)
        return self.get(user.id)

    def reactivate(self, person_id: int) -> PersonAdminOut:
        self._need_org()
        user = self._person(person_id)
        if user.status is not UserStatus.DEACTIVATED:
            raise ConflictError(f"{user.name} is not deactivated")
        self._change_status(user, UserStatus.ACTIVE)
        return self.get(user.id)

    # ------------------------------------------------------------ sign-in and rights (users.manage)

    def update_sign_in(self, person_id: int, data: SignInUpdate) -> PersonAdminOut:
        self._need_users()
        user = self._person(person_id)
        changes: dict[str, object] = {}
        if "username" in data.model_fields_set:
            username = None if data.username is None else data.username.strip().lower()
            if username is not None:
                if USERNAME.fullmatch(username) is None:
                    raise RuleViolationError(
                        "a username has lowercase letters, digits, dots, dashes and underscores"
                    )
                clash = self.session.scalar(select(User.id).where(User.username == username))
                if clash is not None and clash != user.id:
                    raise ConflictError(f"the username {username} is taken")
            if username != user.username:
                user.username = changes["username"] = username
                if username is None:
                    user.password_hash = None  # without a name there is no password sign-in
                    user.must_change_password = False
                    sessions.end_all_sessions(self.session, user.id)
        if "email" in data.model_fields_set:
            email = None if data.email is None else data.email.strip().lower()
            if email is not None:
                clash = self.session.scalar(select(User.id).where(User.email == email))
                if clash is not None and clash != user.id:
                    raise ConflictError(f"another person already uses {email}")
            if email != user.email:
                user.email = changes["email"] = email
        if changes:
            self._record("user.sign_in_changed", user, **changes)
        self.session.commit()
        return self.get(user.id)

    def reset_password(self, person_id: int, data: PasswordReset) -> PasswordResetOut:
        """Set a password (given, or generated and shown once); it must be changed at sign-in."""
        self._need_users()
        user = self._person(person_id)
        if user.username is None:
            raise RuleViolationError("give the person a username first")
        password = data.password or generate_password()
        if data.password is not None and (problems := password_problems(password)):
            raise RuleViolationError("password " + "; ".join(problems))
        user.password_hash = hash_password(password)
        user.must_change_password = True
        sessions.end_all_sessions(self.session, user.id)
        self._record("user.password_reset", user)
        self.session.commit()
        return PasswordResetOut(generated_password=None if data.password else password)

    def set_status(self, person_id: int, status: UserStatus) -> PersonAdminOut:
        """Suspend or reactivate the sign-in; suspending ends their sessions (AUTH-4)."""
        if status is UserStatus.DEACTIVATED:
            raise RuleViolationError("deactivating a person is a separate action (org.manage)")
        user = self._person(person_id)
        AccessService(self.session, self.principal).set_status(user.id, status)
        return self.get(user.id)

    def assign(self, person_id: int, data: AssignmentIn) -> PersonAdminOut:
        user = self._person(person_id)
        AccessService(self.session, self.principal).assign_role(user.id, data.role_key, data.scope)
        return self.get(user.id)

    def unassign(self, person_id: int, assignment_id: int) -> PersonAdminOut:
        access = AccessService(self.session, self.principal)
        user = self._person(person_id)
        owner = self.session.scalar(
            select(RoleAssignment.user_id).where(RoleAssignment.id == assignment_id)
        )
        if owner != user.id:
            raise NotFoundError(f"no assignment {assignment_id} for this person")
        access.remove_assignment(assignment_id)
        return self.get(user.id)
