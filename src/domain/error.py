from __future__ import annotations


class DomainError(Exception):
    """Base class for expected domain failures."""

    code = "domain.error"
    retryable = False
