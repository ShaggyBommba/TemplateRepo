from __future__ import annotations

from fastapi.testclient import TestClient

from application.app import get_app
from application.dto import Principal
from application.error import AuthFailed, Forbidden
from presentation.api.app import api


def test_me_requires_bearer_token() -> None:
    client = client_for(FakeApp(Principal("user-123", "admin", frozenset())))

    response = client.get("/me")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "auth.missing_token"
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_invalid_bearer_token() -> None:
    client = client_for(FakeApp(None))

    response = client.get("/me", headers={"Authorization": "Bearer bad"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "auth.invalid_token"


def test_me_rejects_principal_without_required_role() -> None:
    client = client_for(FakeApp(Principal("user-123", "user", frozenset())))

    response = client.get("/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "auth.forbidden"


def test_me_returns_principal_with_users_read_role() -> None:
    client = client_for(
        FakeApp(
            Principal(
                subject="user-123",
                username="admin",
                roles=frozenset({"users:read", "users:create"}),
            )
        )
    )

    response = client.get("/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json() == {
        "subject": "user-123",
        "username": "admin",
        "roles": ["users:create", "users:read"],
    }


def client_for(fake: FakeApp) -> TestClient:
    app = api()
    app.dependency_overrides[get_app] = lambda: fake
    return TestClient(app)


class FakeApp:
    def __init__(self, result: Principal | None) -> None:
        self.result = result

    def authorize(self, token: str, role: str) -> Principal:
        if self.result is None:
            raise AuthFailed("bad token")
        if not self.result.has(role):
            raise Forbidden("missing role")
        return self.result
