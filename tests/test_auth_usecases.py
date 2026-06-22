from __future__ import annotations

import pytest

from application.dto import Principal
from application.error import AuthFailed, Forbidden
from application.usecases.auth import Authenticate, Authorize


def test_authenticate_returns_trusted_principal() -> None:
    principal = Principal("user-123", "admin", frozenset({"users:read"}))
    authenticate = Authenticate(FakeVerifier(principal))

    assert authenticate("token") == principal


def test_authenticate_rejects_untrusted_token() -> None:
    authenticate = Authenticate(FakeVerifier(None))

    with pytest.raises(AuthFailed):
        authenticate("token")


def test_authorize_returns_principal_with_required_role() -> None:
    principal = Principal("user-123", "admin", frozenset({"users:read"}))
    authorize = Authorize(FakeVerifier(principal))

    assert authorize("token", "users:read") == principal


def test_authorize_rejects_untrusted_token() -> None:
    authorize = Authorize(FakeVerifier(None))

    with pytest.raises(AuthFailed):
        authorize("token", "users:read")


def test_authorize_rejects_principal_without_required_role() -> None:
    principal = Principal("user-123", "user", frozenset())
    authorize = Authorize(FakeVerifier(principal))

    with pytest.raises(Forbidden):
        authorize("token", "users:read")


class FakeVerifier:
    def __init__(self, principal: Principal | None) -> None:
        self.principal = principal

    def get(self, token: str) -> Principal | None:
        return self.principal
