"""Server-side login sessions: the cookie carries a random token, the database only its hash.

Because every request looks the session up, logging out, expiring or suspending an account
takes effect immediately (AUTH-4).
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.models import User, UserSession
from momato.db.models.people import UserStatus

SESSION_COOKIE = "momato_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(
    session: Session,
    user: User,
    *,
    lifetime: timedelta,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Create a session for `user` and return the token to put in the cookie."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    session.add(
        UserSession(
            token_hash=_hash(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + lifetime,
            last_seen_at=now,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return token


def user_for_token(session: Session, token: str | None) -> User | None:
    """The active user owning a valid, unexpired session token; None otherwise."""
    if not token:
        return None
    row = session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == _hash(token))
    ).first()
    if row is None:
        return None
    user_session, user = row
    if user_session.expires_at <= utcnow() or user.status is not UserStatus.ACTIVE:
        return None
    return user


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))


def end_all_sessions(session: Session, user_id: int, *, except_token: str | None = None) -> None:
    """Log a person out everywhere (after a password change, a suspension, a deactivation)."""
    query = delete(UserSession).where(UserSession.user_id == user_id)
    if except_token:
        query = query.where(UserSession.token_hash != _hash(except_token))
    session.execute(query)


def purge_expired(session: Session) -> None:
    session.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
