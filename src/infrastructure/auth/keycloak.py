from __future__ import annotations

from logging import getLogger

import jwt
from jwt.exceptions import PyJWTError

from application.dto import Principal
from infrastructure.config import KeycloakSettings
from infrastructure.error import AuthError

logger = getLogger(__name__)


class KeycloakVerifier:
    """Verify Keycloak JWT access tokens and extract client roles."""

    def __init__(self, settings: KeycloakSettings) -> None:
        self.settings = settings
        self.client = jwt.PyJWKClient(self.settings.jwks_url)

    def get(self, token: str) -> Principal | None:
        try:
            return self.verify(token)
        except AuthError as exc:
            logger.debug("Rejected Keycloak token: %s", exc)
            return None

    def verify(self, token: str) -> Principal:
        try:
            # 1. Automatically extracts 'kid', grabs it from cache, or fetches from Keycloak
            signing_key = self.client.get_signing_key_from_jwt(token)

            # 2. Decodes and validates claims
            payload = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=list(self.settings.algorithms),
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"verify_aud": self.settings.audience is not None},
            )
        except PyJWTError as exc:
            raise AuthError("invalid access token") from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthError("access token is missing subject")

        return Principal(
            subject=subject,
            username=payload.get("preferred_username"),
            roles=frozenset(
                (
                    payload.get("resource_access", {})
                    .get(self.settings.client_id, {})
                    .get("roles", [])
                )
            ),
        )
