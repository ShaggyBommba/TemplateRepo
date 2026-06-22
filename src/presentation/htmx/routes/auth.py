"""HTMX browser login and logout routes."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from infrastructure.config import KeycloakSettings, get_settings
from presentation.htmx import security

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


@routes.get("/callback")
def callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = get_settings()
    response = RedirectResponse("/")
    security.pop_state(response, settings.session)

    if not security.valid_state(request, settings.session, state):
        raise HTTPException(400, "invalid login state")

    redirect_uri = str(request.url_for("callback"))
    try:
        token = exchange(settings.keycloak, code, redirect_uri)
        user = userinfo(settings.keycloak, token["access_token"])
    except httpx.HTTPError as exc:
        raise HTTPException(400, "login failed") from exc
    security.set_session(
        response,
        settings.session,
        {
            "subject": str(user.get("sub", "")),
            "username": str(
                user.get("preferred_username")
                or user.get("email")
                or user.get("sub")
                or "user"
            ),
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
