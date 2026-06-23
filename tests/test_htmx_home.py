from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from application.app import get_app
from application.dto import Principal
from presentation.htmx.app import api
from presentation.htmx.routes import auth as auth_routes
from utils import signing


def test_htmx_surface_exposes_expected_routes() -> None:
    paths = api().openapi()["paths"]

    assert set(paths) == {
        "/",
        "/admin",
        "/admin/heartbeat",
        "/auth/callback/verify",
        "/callback",
        "/health",
        "/login",
        "/logout",
        "/status",
        "/version",
    }


def test_homepage_renders_basic_template_shell() -> None:
    client = client_for(FakeApp())

    response = client.get("/")

    assert response.status_code == 200
    assert "template-app" in response.text
    assert "<h1>Home</h1>" in response.text
    assert "Workspace" in response.text
    assert "SaaS template" in response.text
    assert "/static/css/app.css" in response.text
    assert "/static/vendor/htmx.min.js" in response.text
    assert "/static/vendor/alpinejs.min.js" in response.text
    assert "0.9.0" in response.text
    assert "Ready" in response.text
    assert 'href="/login"' in response.text
    assert 'href="/system"' not in response.text
    assert "Service pipeline" not in response.text
    assert "Recent activity" not in response.text
    assert 'href="/admin"' not in response.text


def test_homepage_renders_logged_in_non_admin_user_without_admin_nav() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "viewer",
                "roles": ["users:read"],
            }
        ),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "viewer" in response.text
    assert 'href="/logout"' in response.text
    assert 'href="/admin"' not in response.text


def test_homepage_renders_admin_nav_for_user_with_create_role() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "admin",
                "roles": ["users:create", "users:read"],
            }
        ),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "admin" in response.text
    assert 'href="/logout"' in response.text
    assert 'href="/admin"' in response.text


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


def test_home_hx_request_returns_content_fragment_without_document() -> None:
    client = client_for(FakeApp())

    response = client.get("/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert "<html" not in response.text.lower()
    assert "<h1>Home</h1>" in response.text
    # the content block excludes the shell and navbar
    assert "SaaS template" not in response.text


def test_system_pane_is_not_registered() -> None:
    client = client_for(FakeApp(healthy=False))

    response = client.get("/system")

    assert response.status_code == 404


def test_admin_page_redirects_anonymous_user_to_login() -> None:
    client = client_for(FakeApp())

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://testserver/login"


def test_admin_page_rejects_user_without_create_role() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "viewer",
                "roles": ["users:read"],
            }
        ),
    )

    response = client.get("/admin")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "auth.forbidden"
    assert response.json()["detail"]["message"] == "Missing required role: users:create"


def test_admin_page_renders_heartbeat_trigger() -> None:
    client = client_for(FakeApp())
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "admin",
                "roles": ["users:create", "users:read"],
            }
        ),
    )

    response = client.get("/admin")

    assert response.status_code == 200
    assert "Start heartbeat" in response.text
    assert "startHeartbeat()" in response.text
    assert "/admin/heartbeat" in response.text


def test_admin_heartbeat_enqueues_job_for_admin() -> None:
    app = FakeApp()
    client = client_for(app)
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "admin",
                "roles": ["users:create", "users:read"],
            }
        ),
    )

    response = client.post("/admin/heartbeat", json={"beats": 5})

    assert response.status_code == 202
    assert response.json() == {"job_id": "job-hb"}
    assert app.heartbeat_calls == [(5, None)]


def test_admin_heartbeat_uses_defaults_when_body_empty() -> None:
    app = FakeApp()
    client = client_for(app)
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "admin",
                "roles": ["users:create", "users:read"],
            }
        ),
    )

    response = client.post("/admin/heartbeat", json={})

    assert response.status_code == 202
    assert app.heartbeat_calls == [(None, None)]


def test_admin_heartbeat_rejects_anonymous_user() -> None:
    app = FakeApp()
    client = client_for(app)

    response = client.post("/admin/heartbeat", json={})

    assert response.status_code == 401
    assert app.heartbeat_calls == []


def test_admin_heartbeat_rejects_user_without_create_role() -> None:
    app = FakeApp()
    client = client_for(app)
    client.cookies.set(
        "template_session",
        signed_session(
            {
                "subject": "user-123",
                "username": "viewer",
                "roles": ["users:read"],
            }
        ),
    )

    response = client.post("/admin/heartbeat", json={})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "auth.forbidden"
    assert app.heartbeat_calls == []


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
    session = signing.read(
        verify.cookies["template_session"],
        api_settings().session.secret_key.get_secret_value(),
    )
    assert session is not None
    assert session["roles"] == ["users:create", "users:read"]
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


def test_static_assets_are_served() -> None:
    client = client_for(FakeApp())

    for path in (
        "/static/vendor/htmx.min.js",
        "/static/vendor/alpinejs.min.js",
        "/static/css/app.css",
    ):
        assert client.get(path).status_code == 200, path


def client_for(app: FakeApp) -> TestClient:
    htmx_app = api()
    htmx_app.dependency_overrides[get_app] = lambda: app
    return TestClient(htmx_app)


def api_settings():
    from infrastructure.config import Settings

    return Settings()


def signed_session(data: dict[str, object]) -> str:
    return signing.sign(
        data,
        api_settings().session.secret_key.get_secret_value(),
    )


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
        self.heartbeat_calls: list[tuple[int | None, float | None]] = []

    def authenticate(self, token: str) -> Principal:
        return Principal(
            subject="user-123",
            username="admin",
            roles=frozenset({"users:create", "users:read"}),
        )

    def request_heartbeat(
        self,
        beats: int | None = None,
        interval: float | None = None,
    ) -> SimpleNamespace:
        self.heartbeat_calls.append((beats, interval))
        return SimpleNamespace(id="job-hb")
