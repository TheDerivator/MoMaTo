"""Translate domain exceptions into HTTP responses, in one place.

Every error response has the shape `{"error": "<code>", "message": "<human text>"}`. Request
validation errors keep FastAPI's standard 422 format.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from momato.domain import errors

# Most specific first: the first matching class wins.
_STATUS: list[tuple[type[Exception], int, str]] = [
    (errors.TooManyAttemptsError, 429, "too_many_attempts"),
    (errors.PasswordChangeRequiredError, 403, "password_change_required"),
    (errors.PermissionDeniedError, 403, "permission_denied"),
    (errors.AuthenticationRequiredError, 401, "authentication_required"),
    (errors.InvalidCredentialsError, 401, "invalid_credentials"),
    (errors.NotFoundError, 404, "not_found"),
    (errors.StaleVersionError, 409, "stale"),
    (errors.ConflictError, 409, "conflict"),
    (errors.RuleViolationError, 422, "rule_violation"),
    (errors.DomainError, 400, "bad_request"),
    (StaleDataError, 409, "stale"),
]


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def _handle(_request: Request, exc: Exception) -> JSONResponse:
    for exc_type, status, code in _STATUS:
        if isinstance(exc, exc_type):
            message = (
                "someone else changed this in the meantime; reload and try again"
                if isinstance(exc, StaleDataError)
                else str(exc)
            )
            response = error_response(status, code, message)
            if isinstance(exc, errors.TooManyAttemptsError):
                response.headers["Retry-After"] = str(exc.retry_after_seconds)
            return response
    raise exc  # pragma: no cover  (only registered for the classes above)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.DomainError, _handle)
    app.add_exception_handler(StaleDataError, _handle)
