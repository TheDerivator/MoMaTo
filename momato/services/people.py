"""People as everyone else sees them: persons who work here, never system accounts (D-012)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.db.models import User
from momato.db.models.people import UserKind, UserStatus


def active_people(session: Session) -> list[User]:
    """Persons who work here, by name: what pickers, planning rows and the people list are made of.

    The built-in `admin` and `anonymous` are system accounts and never appear; deactivated people
    are left out of pickers (they keep their history). A person whose sign-in is only suspended
    still works here, so they stay (ADM-2, ADM-3, D-057).
    """
    return list(
        session.scalars(
            select(User)
            .where(User.kind == UserKind.PERSON, User.status != UserStatus.DEACTIVATED)
            .order_by(User.name, User.id)
        )
    )
