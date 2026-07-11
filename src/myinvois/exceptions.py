"""Exception hierarchy for the MyInvois SDK.

Errors are mapped to HTTP status codes by `error_for_status`. Each exception
carries the originating `status_code` (when the error came from the API) so
callers can branch on it without re-parsing strings.
"""

from __future__ import annotations

__all__ = [
    "AuthenticationError",
    "MyInvoisError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
    "error_for_status",
]


class MyInvoisError(Exception):
    """Base class for all MyInvois SDK errors.

    `status_code` is `None` for errors that did not originate from an HTTP
    response (e.g. configuration problems, transport errors).
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code: int | None = status_code


class ValidationError(MyInvoisError):
    """HTTP 400 — request body/query was rejected by the LHDN API."""


class AuthenticationError(MyInvoisError):
    """HTTP 401/403 — token missing, expired, or insufficient scope."""

    # Used by the auth layer to signal "the cached token is no longer valid";
    # see auth.py.
    invalid_token: bool = False


class NotFoundError(MyInvoisError):
    """HTTP 404 — requested resource does not exist."""


class RateLimitError(MyInvoisError):
    """HTTP 429 — too many requests."""


def error_for_status(message: str, *, status_code: int) -> MyInvoisError:
    """Map an HTTP status code to the most specific `MyInvoisError` subclass.

    Raises `ValueError` if `status_code` is not a valid HTTP status range.
    """
    if not (100 <= status_code <= 599):
        raise ValueError(f"Not an HTTP status code: {status_code!r}")

    if status_code == 400:
        return ValidationError(message, status_code=status_code)
    if status_code in (401, 403):
        return AuthenticationError(message, status_code=status_code)
    if status_code == 404:
        return NotFoundError(message, status_code=status_code)
    if status_code == 429:
        return RateLimitError(message, status_code=status_code)
    return MyInvoisError(message, status_code=status_code)
