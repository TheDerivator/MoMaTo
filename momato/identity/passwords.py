"""Password hashing (argon2id), verification, rehash checks, and generated initial passwords."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True if `password` matches. Accounts without a hash (SSO-only, anonymous) never match."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash uses outdated parameters and should be replaced at next login."""
    return _hasher.check_needs_rehash(password_hash)


def generate_password() -> str:
    """A random password for generated accounts, e.g. the first admin (URL-safe, ~128 bits)."""
    return secrets.token_urlsafe(16)


def password_problems(password: str) -> list[str]:
    """Human-readable reasons a new password is refused (empty list = acceptable)."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        problems.append("must not start or end with spaces")
    return problems
