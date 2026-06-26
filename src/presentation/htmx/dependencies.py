"""Shared dependencies for the HTMX presentation surface."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response
from jinja2_fragments.fastapi import Jinja2Blocks
from pydantic import BaseModel

from application.app import App


class SurfaceState(BaseModel):
    name: str
    version: str
    healthy: bool
    status: str


def template_engine(request: Request) -> Jinja2Blocks:
    return request.app.state.templates


def render(
    request: Request,
    templates: Jinja2Blocks,
    name: str,
    context: dict[str, Any],
    *,
    block: str = "content",
) -> Response:
    """Render a full page, or just the content block for targeted HTMX swaps.

    Boosted navigation (``HX-Boosted``) still needs the whole document so the
    shell and ``<title>`` swap correctly; only non-boosted HTMX requests that
    target a region inside the page receive the lighter block fragment.
    """
    targeted = request.headers.get("HX-Request") and not request.headers.get(
        "HX-Boosted"
    )
    if targeted:
        return templates.TemplateResponse(request, name, context, block_name=block)
    return templates.TemplateResponse(request, name, context)


def surface_state(app: App) -> SurfaceState:
    healthy = app.healthy
    return SurfaceState(
        name=app.name,
        version=app.version,
        healthy=healthy,
        status="Ready" if healthy else "Unavailable",
    )
