from __future__ import annotations


class ApplicationError(Exception):
    """Base class for expected application failures."""

    code = "application.error"
    retryable = False


class BillNotFound(ApplicationError):
    code = "bill.not_found"


class AuthFailed(ApplicationError):
    code = "auth.failed"


class Forbidden(ApplicationError):
    code = "auth.forbidden"
