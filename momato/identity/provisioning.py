"""Map an external (SSO) identity to a person, honouring what an administrator prepared (AUTH-3).

Order of matching:
1. A person already linked to (provider, subject) is that person.
2. Otherwise a person whose email equals the identity's email (prepared in advance by an
   administrator, with their rights) is linked to it.
3. Otherwise (providers without email, such as Windows sign-in) a person whose login name equals
   the identity's login name hint is linked the same way.
4. Otherwise, per configuration: rejected (invite-only), or created without any rights.
System accounts are never linked. Suspended and deactivated people are refused whatever the
provider says. The identity's groups are remembered for group → role mappings.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato.config import UnknownUserPolicy
from momato.db.base import normalize_email, utcnow
from momato.db.models import ExternalIdentity as IdentityLink
from momato.db.models import User
from momato.db.models.people import UserKind, UserStatus
from momato.domain.errors import InvalidCredentialsError, PermissionDeniedError
from momato.domain.usernames import unique_username
from momato.identity.providers import ExternalIdentity

LAST_SEEN_RESOLUTION = timedelta(hours=1)


def resolve_user(
    session: Session, identity: ExternalIdentity, unknown_users: UnknownUserPolicy
) -> tuple[User, str]:
    """The person for `identity`, plus what happened ("known", "linked" or "created")."""
    link = session.scalars(
        select(IdentityLink).where(
            IdentityLink.provider == identity.provider, IdentityLink.subject == identity.subject
        )
    ).one_or_none()
    outcome = "known"
    if link is not None:
        user = session.get(User, link.user_id)
        if user is None:  # the link outlived its person: cannot happen with foreign keys
            raise InvalidCredentialsError("this sign-in belongs to no account")
    else:
        user, outcome = _link_or_create(session, identity, unknown_users)
        link = IdentityLink(user_id=user.id, provider=identity.provider, subject=identity.subject)
        session.add(link)

    if user.status is UserStatus.SUSPENDED:
        raise PermissionDeniedError("this account is suspended")
    if user.status is UserStatus.DEACTIVATED:
        raise PermissionDeniedError("this account is deactivated")
    groups = sorted(set(identity.groups))
    if (link.groups or []) != groups:
        link.groups = groups
    now = utcnow()
    # Ambient providers identify every request: only write "last seen" once in a while.
    if link.last_seen_at is None or now - link.last_seen_at > LAST_SEEN_RESOLUTION:
        link.last_seen_at = now
        user.last_login_at = now
    return user, outcome


def _prepared(session: Session, identity: ExternalIdentity, condition: object) -> User | None:
    """A linkable prepared person: a real person, not yet linked to this provider."""
    candidate = session.scalars(
        select(User).where(condition, User.kind == UserKind.PERSON)  # type: ignore[arg-type]
    ).one_or_none()
    if candidate is None:
        return None
    already = session.scalar(
        select(IdentityLink.id).where(
            IdentityLink.user_id == candidate.id, IdentityLink.provider == identity.provider
        )
    )
    return None if already is not None else candidate


def _link_or_create(
    session: Session, identity: ExternalIdentity, unknown_users: UnknownUserPolicy
) -> tuple[User, str]:
    email = normalize_email(identity.email)
    if email and (prepared := _prepared(session, identity, User.email == email)):
        return prepared, "linked"
    if identity.username and (
        prepared := _prepared(session, identity, User.username == identity.username.lower())
    ):
        return prepared, "linked"
    if unknown_users is UnknownUserPolicy.CREATE:
        name = identity.display_name or email or identity.subject
        taken = set(session.scalars(select(User.username).where(User.username.is_not(None))))
        user = User(
            kind=UserKind.PERSON,
            name=name,
            username=unique_username(identity.username or email or name, {t for t in taken if t}),
            email=email,
        )
        session.add(user)
        session.flush()
        return user, "created"
    raise InvalidCredentialsError("no account has been set up for you; ask an administrator")
