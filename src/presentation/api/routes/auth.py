"""Authenticated API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from application.dto import Principal
from presentation.api.dependencies import require

routes = APIRouter(tags=["auth"])


class PrincipalResponse(BaseModel):
    subject: str
    username: str | None
    roles: list[str]

    @classmethod
    def from_principal(cls, principal: Principal) -> PrincipalResponse:
        return cls(
            subject=principal.subject,
            username=principal.username,
            roles=sorted(principal.roles),
        )


@routes.get("/me")
def me(
    principal: Principal = Depends(require("users:read")),
) -> PrincipalResponse:
    return PrincipalResponse.from_principal(principal)
