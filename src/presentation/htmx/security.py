from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from infrastructure.config import SessionSettings


def get(request: Request, settings: SessionSettings) -> dict[str, Any] | None:
    """Extract and decode the signed session dictionary from the incoming request cookies.

    Args:
        request: The incoming FastAPI request containing browser cookies.
        settings: Configuration settings for the session (cookie name, keys, etc.).

    Returns:
        The decoded dictionary payload if the signature is valid, or None if missing or tampered with.
    """
    value = request.cookies.get(settings.cookie_name)
    return read(value, settings)


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
        sign(data, settings),
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
        sign({"state": state}, settings),
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
    stored = read(request.cookies.get(settings.state_cookie_name), settings)
    return stored is not None and stored.get("state") == state


def read(value: str | None, settings: SessionSettings) -> dict[str, Any] | None:
    """Parse a signed "payload.signature" string, verify its integrity, and decode the JSON.

    Args:
        value: The raw string read from a cookie.
        settings: Session infrastructure configurations providing the hashing secret key.

    Returns:
        The decoded dictionary if the signature matches, or None if verification fails.
    """
    if value is None or "." not in value:
        return None

    payload, signature = value.rsplit(".", 1)
    expected = digest(payload, settings)
    
    # Use hmac.compare_digest to defend against timing attacks
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        raw = base64.urlsafe_b64decode(pad(payload))
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def sign(data: dict[str, Any], settings: SessionSettings) -> str:
    """Convert a dictionary to compact JSON, base64-encode it, and append an HMAC signature.

    Args:
        data: The dictionary data payload to sign.
        settings: Session infrastructure configurations providing the secret key.

    Returns:
        A combined string formatted securely as "payload.signature".
    """
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{payload}.{digest(payload, settings)}"


def digest(payload: str, settings: SessionSettings) -> str:
    """Compute a SHA256 HMAC digest hex string over a text payload using the session secret key.

    Args:
        payload: The base64 URL text segment requiring a signature.
        settings: Session configurations holding the secret key value.

    Returns:
        The cryptographic hex digest signature.
    """
    secret = settings.secret_key.get_secret_value().encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def pad(value: str) -> str:
    """Append required base64 padding characters ('=') to a truncated string based on alignment.

    Args:
        value: A string missing base64 padding characters.

    Returns:
        The appropriately padded string ready for standard decoding.
    """
    return value + "=" * (-len(value) % 4)