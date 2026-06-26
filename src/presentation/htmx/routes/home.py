"""Template homepage routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from jinja2_fragments.fastapi import Jinja2Blocks

from application.app import App, get_app
from infrastructure.config import get_settings
from presentation.htmx import security
from presentation.htmx.dependencies import render, surface_state, template_engine

routes = APIRouter(tags=["home"])


@routes.get("/", response_class=HTMLResponse, name="index")
def index(
    request: Request,
    app: App = Depends(get_app),
    templates: Jinja2Blocks = Depends(template_engine),
) -> Response:
    settings = get_settings()
    return render(
        request,
        templates,
        "home/index.html",
        {
            "state": surface_state(app).model_dump(),
            "user": security.get(request, settings.session),
        },
    )


@routes.get("/status")
def status(app: App = Depends(get_app)) -> dict[str, str | bool]:
    return surface_state(app).model_dump()


@routes.get("/health")
def health(app: App = Depends(get_app)) -> dict[str, bool]:
    return {"healthy": app.healthy}


@routes.get("/version")
def version(app: App = Depends(get_app)) -> dict[str, str]:
    return {"version": app.version}
