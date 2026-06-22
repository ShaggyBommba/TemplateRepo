"""System HTMX and health routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2_fragments.fastapi import Jinja2Blocks

from application.app import App, get_app
from infrastructure.config import get_settings
from presentation.htmx import security
from presentation.htmx.dependencies import render, surface_state, template_engine

routes = APIRouter(tags=["system"])


@routes.get("/system", response_class=HTMLResponse, name="system_index")
def system_index(
    request: Request,
    app: App = Depends(get_app),
    templates: Jinja2Blocks = Depends(template_engine),
) -> HTMLResponse:
    settings = get_settings()
    return render(
        request,
        templates,
        "system/index.html",
        {
            "state": surface_state(app).model_dump(),
            "user": security.get(request, settings.session),
        },
    )


@routes.get("/health")
def health(app: App = Depends(get_app)) -> dict[str, bool]:
    return {"healthy": app.healthy}


@routes.get("/version")
def version(app: App = Depends(get_app)) -> dict[str, str]:
    return {"version": app.version}
