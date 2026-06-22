from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from application.app import get_app
from presentation.htmx.app import api
from presentation.htmx.features.auth import routes as auth_routes
from utils import signing


def test_htmx_surface_exposes_expected_routes() -> None:
    paths = api().openapi()["paths"]

    assert set(paths) == {
        "/",
        "/auth/callback/verify",
        "/callback",
        "/health",
        "/login",
        "/logout",
        "/status",
        "/system",
        "/version",
    }


def test_homepage_renders_basic_template_shell() -> None:
    client = client_for(FakeApp())

    response = client.get("/")

    assert response.status_code == 200
    assert "template-app" in response.text
    assert "Layered service template" in response.text
    assert "htmx.org@2.0.4" in response.text
    assert "alpinejs@3.14.8" in response.text
    assert "@click" in response.text
    assert 'fetch("/status"' in response.text
    assert "0.9.0" in response.text
    assert "Ready" in response.text
    assert 'href="/login"' in response.text


def test_homepage_renders_logged_in_user() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signing.sign(
            {"subject": "user-123", "username": "admin"},
            api_settings().session.secret_key.get_secret_value(),
        ),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "admin" in response.text
    assert 'href="/logout"' in response.text


def test_status_returns_current_app_state_json() -> None:
    client = client_for(FakeApp(healthy=False))

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json() == {
        "name": "template-app",
        "version": "0.9.0",
        "healthy": False,
        "status": "Unavailable",
    }


def test_system_page_renders_feature_template() -> None:
    client = client_for(FakeApp(healthy=False))

    response = client.get("/system")

    assert response.status_code == 200
    assert "<h1>System</h1>" in response.text
    assert "Unavailable" in response.text
    assert 'href="/status"' in response.text


def test_login_redirects_to_keycloak_and_sets_state_cookie() -> None:
    client = client_for(FakeApp())

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert location.startswith(
        "http://localhost:8080/realms/template/protocol/openid-connect/auth?"
    )
    assert query["client_id"] == ["template"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["http://testserver/callback"]
    assert query["scope"] == ["openid profile email"]
    assert "template_oauth_state" in response.cookies


def test_callback_renders_oauth_state_page() -> None:
    client = client_for(FakeApp())

    response = client.get("/callback?code=code&state=state")

    assert response.status_code == 200
    assert 'hx-get="/auth/callback/verify"' in response.text
    assert 'hx-trigger="load"' in response.text
    assert 'x-data="authCallback()"' in response.text
    assert 'value="code"' in response.text
    assert 'value="state"' in response.text


def test_callback_verify_rejects_invalid_state() -> None:
    client = client_for(FakeApp())

    response = client.get("/auth/callback/verify?code=code&state=bad")

    assert response.status_code == 400
    assert response.text == "Invalid login state."


def test_callback_verify_exchanges_code_and_stores_session(monkeypatch) -> None:
    client = client_for(FakeApp())
    login = client.get("/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    monkeypatch.setattr(auth_routes.httpx, "post", fake_token)
    monkeypatch.setattr(auth_routes.httpx, "get", fake_userinfo)

    page = client.get(f"/callback?code=code&state={state}")
    verify = client.get(
        f"/auth/callback/verify?code=code&state={state}",
        follow_redirects=False,
    )
    home = client.get("/")

    assert page.status_code == 200
    assert verify.status_code == 200
    assert 'data-auth-state="success"' in verify.text
    assert 'data-redirect-to="/"' in verify.text
    assert "template_session" in verify.cookies
    assert "admin" in home.text


def test_logout_clears_session_and_redirects_to_keycloak() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signing.sign(
            {"subject": "user-123", "username": "admin"},
            api_settings().session.secret_key.get_secret_value(),
        ),
    )

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "http://localhost:8080/realms/template/protocol/openid-connect/logout?"
    )
    assert "template_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def client_for(app: FakeApp) -> TestClient:
    htmx_app = api()
    htmx_app.dependency_overrides[get_app] = lambda: app
    return TestClient(htmx_app)


def api_settings():
    from infrastructure.config import Settings

    return Settings()


def fake_token(*args, **kwargs) -> FakeResponse:
    return FakeResponse({"access_token": "access-token"})


def fake_userinfo(*args, **kwargs) -> FakeResponse:
    return FakeResponse({"sub": "user-123", "preferred_username": "admin"})


class FakeResponse:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return self.data


class FakeApp:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.name = "template-app"
        self.version = "0.9.0"
