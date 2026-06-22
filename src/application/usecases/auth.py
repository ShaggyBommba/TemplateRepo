from __future__ import annotations

from application.adapters.core import TokenVerifier
from application.dto import Principal
from application.error import AuthFailed, Forbidden


class Authorize:
    """Authenticate one bearer token and require one role."""

    def __init__(self, verifier: TokenVerifier) -> None:
        self.verifier = verifier

    def __call__(self, token: str, role: str) -> Principal:
        principal = self.verifier.get(token)
        if principal is None:
            raise AuthFailed("bearer token was not trusted")
        if not principal.has(role):
            raise Forbidden(f"missing required role: {role}")
        return principal
