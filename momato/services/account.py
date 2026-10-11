"""The signed-in person's own record for the Profile page (ADM-8): data and availability."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import Availability, OrgNode, User
from momato.domain.errors import AuthenticationRequiredError, NotFoundError
from momato.domain.fields import Profile
from momato.identity.principal import Principal
from momato.schemas.account import AccountOut
from momato.services.people_admin import availability_rows, work_pattern


class AccountService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        if principal.is_anonymous:
            raise AuthenticationRequiredError("log in to see your profile")

    def _path(self, node_id: int | None) -> Sequence[OrgNode]:
        path: list[OrgNode] = []
        current = node_id
        while current is not None:
            node = self.session.get(OrgNode, current)
            if node is None:
                break
            path.append(node)
            current = node.parent_id
        return list(reversed(path))

    def account(self) -> AccountOut:
        user = self.session.get(User, self.principal.user_id)
        if user is None:
            raise NotFoundError("no such account")
        overrides: dict[int, Decimal] = {
            row.year: row.days
            for row in self.session.scalars(
                select(Availability).where(Availability.user_id == user.id)
            )
        }
        path = self._path(user.org_node_id)
        department = next((n.name for n in reversed(path) if n.is_department), None)
        return AccountOut(
            id=user.id,
            name=user.name,
            job_title=user.job_title,
            org_path=[n.name for n in path if n.parent_id is not None],
            department=department,
            hue=user.hue,
            username=user.username,
            email=user.email,
            work_minutes=list(work_pattern(user).minutes),
            availability=availability_rows(user, overrides, self.profile, self.today),
            password_sign_in=user.password_hash is not None,
            must_change_password=user.must_change_password,
        )
