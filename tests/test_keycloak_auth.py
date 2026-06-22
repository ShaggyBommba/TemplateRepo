from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode

from infrastructure.auth.keycloak import KeycloakVerifier
from infrastructure.config import KeycloakSettings, Settings
from infrastructure.error import AuthError


def test_keycloak_settings_builds_realm_urls() -> None:
    settings = Settings(
        keycloak=KeycloakSettings(
            base_url="http://keycloak:8080/",
            realm="template",
        )
    )

    assert settings.keycloak.issuer == "http://keycloak:8080/realms/template"
    assert (
        settings.keycloak.jwks_url
        == "http://keycloak:8080/realms/template/protocol/openid-connect/certs"
    )


def test_verifier_extracts_client_roles_from_valid_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = KeycloakSettings(base_url="http://keycloak:8080")
    token = access_token(
        private_key,
        kid="test-key",
        issuer=settings.issuer,
        roles=["users:create", "users:read"],
    )
    verifier = KeycloakVerifier(
        settings,
        jwks_loader=lambda: jwks(private_key, "test-key"),
    )

    principal = verifier.verify(token)

    assert principal.subject == "user-123"
    assert principal.username == "admin"
    assert principal.roles == frozenset({"users:create", "users:read"})


def test_verifier_caches_signing_keys_until_token_uses_unknown_key() -> None:
    first_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = KeycloakSettings(base_url="http://keycloak:8080")
    responses = [
        jwks(first_key, "first-key"),
        jwks(second_key, "second-key"),
    ]

    def load() -> dict[str, list[dict[str, Any]]]:
        return responses.pop(0)

    verifier = KeycloakVerifier(settings, jwks_loader=load)
    first_token = access_token(
        first_key,
        kid="first-key",
        issuer=settings.issuer,
        roles=["users:read"],
    )
    second_token = access_token(
        second_key,
        kid="second-key",
        issuer=settings.issuer,
        roles=["users:read"],
    )

    assert verifier.verify(first_token).subject == "user-123"
    assert verifier.verify(first_token).subject == "user-123"
    assert len(responses) == 1
    assert verifier.verify(second_token).subject == "user-123"
    assert responses == []


def test_verifier_rejects_unknown_signing_key() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = KeycloakSettings(base_url="http://keycloak:8080")
    token = access_token(
        private_key,
        kid="missing-key",
        issuer=settings.issuer,
        roles=["users:read"],
    )
    verifier = KeycloakVerifier(
        settings,
        jwks_loader=lambda: jwks(other_key, "other-key"),
    )

    with pytest.raises(AuthError):
        verifier.verify(token)


def test_verifier_rejects_unavailable_signing_keys() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = KeycloakSettings(base_url="http://keycloak:8080")
    token = access_token(
        private_key,
        kid="test-key",
        issuer=settings.issuer,
        roles=["users:read"],
    )
    verifier = KeycloakVerifier(
        settings,
        jwks_loader=lambda: (_ for _ in ()).throw(ValueError("unavailable")),
    )

    with pytest.raises(AuthError):
        verifier.verify(token)

    assert verifier.get(token) is None


def access_token(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
    issuer: str,
    roles: list[str],
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": issuer,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "resource_access": {
                "template": {
                    "roles": roles,
                }
            },
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def jwks(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, list[dict[str, Any]]]:
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": encoded_number(numbers.n),
                "e": encoded_number(numbers.e),
            }
        ]
    }


def encoded_number(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64url_encode(raw).decode()
