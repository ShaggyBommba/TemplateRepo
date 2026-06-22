"""Template homepage routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from application.app import App, get_app
from infrastructure.config import get_settings
from presentation.htmx import security

routes = APIRouter(tags=["home"])

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


class StatusResponse(BaseModel):
    name: str
    version: str
    healthy: bool
    status: str


def state(app: App) -> StatusResponse:
    healthy = app.healthy
    return StatusResponse(
        name=app.name,
        version=app.version,
        healthy=healthy,
        status="Ready" if healthy else "Unavailable",
    )


@routes.get("/", response_class=HTMLResponse)
def index(request: Request, app: App = Depends(get_app)) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "state": state(app).model_dump(),
            "user": security.get(request, settings.session),
        },
    )


@routes.get("/status")
def status(app: App = Depends(get_app)) -> StatusResponse:
    return state(app)
