"""Shared dependencies for the HTMX presentation surface."""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from application.app import App


class SurfaceState(BaseModel):
    name: str
    version: str
    healthy: bool
    status: str


def template_engine(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def surface_state(app: App) -> SurfaceState:
    healthy = app.healthy
    return SurfaceState(
        name=app.name,
        version=app.version,
        healthy=healthy,
        status="Ready" if healthy else "Unavailable",
    )
