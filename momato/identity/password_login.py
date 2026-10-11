"""Username + password login, with throttling against password guessing (AUTH-1).

Failures are counted per account (since its last successful login) and per client address within
a sliding window. Unknown usernames cost the same time as known ones, so response times don't
reveal which accounts exist.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from momato.db.base import normalize_username, utcnow
from momato.db.models import LoginAttempt, User
from momato.db.models.people import UserStatus
from momato.domain.access import ANONYMOUS_USERNAME
from momato.domain.errors import InvalidCredentialsError, TooManyAttemptsError
from momato.identity.passwords import hash_password, needs_rehash, verify_password

# Verified against when the username is unknown, to keep timing uniform.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


@dataclass(frozen=True, slots=True)
class ThrottlePolicy:
    max_failures_per_user: int = 5
    max_failures_per_ip: int = 50
    window: timedelta = timedelta(minutes=15)


def _check_throttle(
    session: Session, username: str, ip_address: str | None, policy: ThrottlePolicy
) -> None:
    window_start = utcnow() - policy.window
    last_success = session.scalar(
        select(func.max(LoginAttempt.at)).where(
            LoginAttempt.username == username, LoginAttempt.success.is_(True)
        )
    )
    since = max(window_start, last_success) if last_success else window_start
    user_failures = session.scalar(
        select(func.count()).where(
            LoginAttempt.username == username,
            LoginAttempt.success.is_(False),
            LoginAttempt.at > since,
        )
    )
    ip_failures = 0
    if ip_address:
        ip_failures = session.scalar(
            select(func.count()).where(
                LoginAttempt.ip_address == ip_address,
                LoginAttempt.success.is_(False),
                LoginAttempt.at > window_start,
            )
        )
    if (user_failures or 0) >= policy.max_failures_per_user or (
        ip_failures or 0
    ) >= policy.max_failures_per_ip:
        raise TooManyAttemptsError(
            "too many failed logins, try again later",
            retry_after_seconds=int(policy.window.total_seconds()),
        )


def authenticate(
    session: Session,
    username: str,
    password: str,
    *,
    ip_address: str | None,
    policy: ThrottlePolicy,
) -> User:
    """Return the user for valid credentials, or raise. Records the attempt either way."""
    name = normalize_username(username) or ""
    _check_throttle(session, name, ip_address, policy)
    user = session.scalars(select(User).where(User.username == name)).one_or_none()
    can_log_in = (
        user is not None
        and user.status is UserStatus.ACTIVE
        and user.username != ANONYMOUS_USERNAME
    )
    password_ok = verify_password(user.password_hash if user else _DUMMY_HASH, password)
    success = can_log_in and password_ok
    session.add(LoginAttempt(username=name, ip_address=ip_address, success=success))
    session.execute(delete(LoginAttempt).where(LoginAttempt.at < utcnow() - timedelta(days=30)))
    if not success or user is None:
        raise InvalidCredentialsError("unknown username or wrong password")
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    return user
