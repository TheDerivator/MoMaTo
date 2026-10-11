"""Domain exceptions. The API layer maps each one to an HTTP status in a single place."""


class DomainError(Exception):
    """Base class: an operation was refused for a business reason."""


class NotFoundError(DomainError):
    """The referenced object does not exist (or is invisible to the caller: SH-11, §6 rule 6)."""


class ConflictError(DomainError):
    """The request conflicts with the current state (a duplicate, a stale version, ...)."""


class StaleVersionError(ConflictError):
    """The object changed since the caller loaded it (optimistic locking, PP-6)."""


class RuleViolationError(DomainError):
    """The request breaks a business rule (a task end before its start, ...)."""


class AuthenticationRequiredError(DomainError):
    """The caller must log in first."""


class PermissionDeniedError(DomainError):
    """The caller is known but not allowed to do this."""


class PasswordChangeRequiredError(PermissionDeniedError):
    """The account must set a new password before doing anything else."""


class InvalidCredentialsError(DomainError):
    """Login failed. Deliberately vague: never reveal whether the username exists."""


class TooManyAttemptsError(DomainError):
    """Too many failed logins; try again later."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
