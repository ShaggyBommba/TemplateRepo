from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response

from infrastructure.config import SessionSettings
from utils import signing


def get(request: Request, settings: SessionSettings) -> dict[str, Any] | None:
    """Extract and decode the signed session dictionary from the incoming request cookies.

    Args:
        request: The incoming FastAPI request containing browser cookies.
        settings: Configuration settings for the session (cookie name, keys, etc.).

    Returns:
        The decoded dictionary payload if the signature is valid, or None if missing or tampered with.
    """
    value = request.cookies.get(settings.cookie_name)
    return signing.read(value, settings.secret_key.get_secret_value())


def set_session(
    response: Response,
    settings: SessionSettings,
    data: dict[str, Any],
) -> None:
    """Serialize, cryptographically sign, and bake the session data into an HttpOnly cookie.

    Args:
        response: The outgoing FastAPI response object.
        settings: Session infrastructure and security rules.
        data: The payload dict to store (e.g., identity, access token).
    """
    response.set_cookie(
        settings.cookie_name,
        signing.sign(data, settings.secret_key.get_secret_value()),
        max_age=settings.max_age_seconds,
        httponly=True,
        secure=settings.secure,
        samesite=settings.same_site,
    )


def clear_session(response: Response, settings: SessionSettings) -> None:
    """Instruct the user's browser to delete the session cookie (used for log out).

    Args:
        response: The outgoing FastAPI response object.
        settings: Session infrastructure rules containing the target cookie name.
    """
    response.delete_cookie(settings.cookie_name)


def set_state(response: Response, settings: SessionSettings, state: str) -> None:
    """Set a short-lived, signed CSRF state cookie prior to redirecting to the OIDC provider.

    Args:
        response: The outgoing FastAPI response object.
        settings: Session infrastructure configurations.
        state: The uniquely generated state string tracking this login request.
    """
    response.set_cookie(
        settings.state_cookie_name,
        signing.sign({"state": state}, settings.secret_key.get_secret_value()),
        max_age=300,  # Strict 5-minute threshold
        httponly=True,
        secure=settings.secure,
        samesite=settings.same_site,
    )


def pop_state(response: Response, settings: SessionSettings) -> None:
    """Remove the OAuth temporary state cookie from the user's browser.

    Args:
        response: The outgoing FastAPI response object.
        settings: Session infrastructure configurations.
    """
    response.delete_cookie(settings.state_cookie_name)


def valid_state(request: Request, settings: SessionSettings, state: str) -> bool:
    """Validate if the callback state parameter matches the signed state cookie.

    Args:
        request: The incoming FastAPI callback request containing cookies.
        settings: Session infrastructure configurations.
        state: The query state string received from the external identity provider.

    Returns:
        True if the state cookie is valid and matches the incoming state argument; False otherwise.
    """
    stored = signing.read(
        request.cookies.get(settings.state_cookie_name),
        settings.secret_key.get_secret_value(),
    )
    return stored is not None and stored.get("state") == state
