from __future__ import annotations


class InfrastructureError(Exception):
    """Base class for expected infrastructure failures."""

    code = "infrastructure.error"
    retryable = False


class AuthError(InfrastructureError):
    code = "auth.invalid_token"
