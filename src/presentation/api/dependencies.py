"""FastAPI dependency wiring."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from application.app import App, get_app
from application.dto import Principal
from application.error import AuthFailed, Forbidden

bearer = HTTPBearer(auto_error=False)


def require(role: str) -> Callable[..., Principal]:
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        app: App = Depends(get_app),
    ) -> Principal:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "auth.missing_token",
                    "message": "Missing bearer token",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            return app.authorize(credentials.credentials, role)
        except AuthFailed as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "auth.invalid_token",
                    "message": "Invalid bearer token",
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except Forbidden as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "auth.forbidden",
                    "message": f"Missing required role: {role}",
                },
            ) from exc

    return dependency
