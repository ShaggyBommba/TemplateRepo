from __future__ import annotations


class ApplicationError(Exception):
    """Base class for expected application failures."""

    code = "application.error"
    retryable = False


class BillNotFound(ApplicationError):
    code = "bill.not_found"


class JobNotFound(ApplicationError):
    code = "job.not_found"

    def __init__(self, job_id: str) -> None:
        super().__init__(f"job not found: {job_id}")


class AuthFailed(ApplicationError):
    code = "auth.failed"


class Forbidden(ApplicationError):
    code = "auth.forbidden"
