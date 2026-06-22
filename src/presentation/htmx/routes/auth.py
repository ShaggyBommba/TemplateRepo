"""HTMX browser login and OAuth callback routes."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates

from application.app import App, get_app
from application.error import AuthFailed
from infrastructure.config import KeycloakSettings, SessionSettings, get_settings
from presentation.htmx import security
from presentation.htmx.dependencies import surface_state, template_engine

routes = APIRouter(tags=["auth"])


@routes.get("/login")
def login(request: Request) -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    redirect_uri = str(request.url_for("callback"))
    params = urlencode(
        {
            "client_id": settings.keycloak.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
        }
    )
    response = RedirectResponse(f"{settings.keycloak.authorization_url}?{params}")
    security.set_state(response, settings.session, state)
    return response


@routes.get("/callback", response_class=HTMLResponse, name="callback")
def callback(
    request: Request,
    code: str = "",
    state: str = "",
    app: App = Depends(get_app),
    templates: Jinja2Templates = Depends(template_engine),
) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "auth/callback.html",
        {
            "state": surface_state(app).model_dump(),
            "user": security.get(request, settings.session),
            "code": code,
            "oauth_state": state,
        },
    )


@routes.get("/auth/callback/verify", response_model=None)
def verify_callback(
    request: Request,
    code: str = "",
    state: str = "",
    app: App = Depends(get_app),
) -> Response:
    settings = get_settings()

    if not code or not state:
        return error("Missing authentication callback parameters.", settings.session)

    if not security.valid_state(request, settings.session, state):
        return error("Invalid login state.", settings.session)

    redirect_uri = str(request.url_for("callback"))
    try:
        token = exchange(settings.keycloak, code, redirect_uri)
        principal = app.authenticate(token["access_token"])
        user = userinfo(settings.keycloak, token["access_token"])
    except HTTPException as exc:
        return error(str(exc.detail), settings.session)
    except AuthFailed:
        return error("Login failed.", settings.session)
    except httpx.HTTPError:
        return error("Login failed.", settings.session)

    response = HTMLResponse(
        '<div data-auth-state="success" data-redirect-to="/">'
        "Authentication succeeded."
        "</div>"
    )
    security.pop_state(response, settings.session)
    security.set_session(
        response,
        settings.session,
        {
            "subject": principal.subject,
            "username": str(
                principal.username
                or user.get("preferred_username")
                or user.get("email")
                or user.get("sub")
                or "user"
            ),
            "roles": sorted(principal.roles),
        },
    )
    return response


@routes.get("/logout")
def logout(request: Request) -> RedirectResponse:
    settings = get_settings()
    redirect_uri = str(request.url_for("index"))
    params = urlencode(
        {
            "client_id": settings.keycloak.client_id,
            "post_logout_redirect_uri": redirect_uri,
        }
    )
    response = RedirectResponse(f"{settings.keycloak.logout_url}?{params}")
    security.clear_session(response, settings.session)
    return response


def error(message: str, settings: SessionSettings) -> PlainTextResponse:
    response = PlainTextResponse(message, status_code=400)
    security.pop_state(response, settings)
    return response


def exchange(
    settings: KeycloakSettings,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    response = httpx.post(
        settings.token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "client_secret": settings.client_secret.get_secret_value(),
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise HTTPException(400, "invalid token response")
    return data


def userinfo(settings: KeycloakSettings, access_token: str) -> dict[str, Any]:
    response = httpx.get(
        settings.userinfo_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(400, "invalid userinfo response")
    return data
