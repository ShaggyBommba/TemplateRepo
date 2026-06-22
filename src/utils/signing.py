from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def read(value: str | None, secret: str) -> dict[str, Any] | None:
    """Return the decoded dictionary when a signed token is valid."""
    if value is None or "." not in value:
        return None

    payload, signature = value.rsplit(".", 1)
    expected = digest(payload, secret)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        raw = base64.urlsafe_b64decode(pad(payload))
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def sign(data: dict[str, Any], secret: str) -> str:
    """Return a compact signed token for a JSON dictionary payload."""
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{payload}.{digest(payload, secret)}"


def digest(payload: str, secret: str) -> str:
    """Return the SHA256 HMAC signature for a payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def pad(value: str) -> str:
    """Return a base64 value with required padding restored."""
    return value + "=" * (-len(value) % 4)
