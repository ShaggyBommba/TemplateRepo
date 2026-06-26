"""Admin HTMX routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from application.app import App, get_app
from infrastructure.config import Settings, get_settings
from presentation.htmx import security
from presentation.htmx.dependencies import surface_state, template_engine

routes = APIRouter(tags=["admin"])
ADMIN_ROLE = "users:create"


@routes.get(
    "/admin",
    response_class=HTMLResponse,
    response_model=None,
    name="admin_index",
)
def admin_index(
    request: Request,
    job_id: str = "",
    app: App = Depends(get_app),
    templates: Jinja2Templates = Depends(template_engine),
) -> HTMLResponse | RedirectResponse:
    settings = get_settings()
    user = security.get(request, settings.session)
    if user is None:
        return RedirectResponse(str(request.url_for("login")))
    if ADMIN_ROLE not in set(user.get("roles") or ()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "auth.forbidden",
                "message": f"Missing required role: {ADMIN_ROLE}",
            },
        )

    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {
            "state": surface_state(app).model_dump(),
            "user": user,
            "job_id": job_id,
            "jobs_ws_url": job_websocket_template(request, settings),
            "heartbeat_url": str(request.url_for("admin_heartbeat")),
        },
    )


class HeartbeatTriggerRequest(BaseModel):
    beats: int | None = Field(default=None, ge=1)
    interval: float | None = Field(default=None, gt=0)


class HeartbeatTriggerResponse(BaseModel):
    job_id: str


@routes.post(
    "/admin/heartbeat",
    status_code=status.HTTP_202_ACCEPTED,
    name="admin_heartbeat",
)
async def admin_heartbeat(
    request: Request,
    payload: HeartbeatTriggerRequest,
    app: App = Depends(get_app),
) -> HeartbeatTriggerResponse:
    settings = get_settings()
    user = security.get(request, settings.session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "auth.unauthenticated", "message": "Sign in required"},
        )
    if ADMIN_ROLE not in set(user.get("roles") or ()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "auth.forbidden",
                "message": f"Missing required role: {ADMIN_ROLE}",
            },
        )

    job = await app.request_heartbeat(payload.beats, payload.interval)
    return HeartbeatTriggerResponse(job_id=job.id)


def job_websocket_template(request: Request, settings: Settings) -> str:
    scheme = "wss" if request.url.scheme == "https" else "ws"
    host = settings.api_host
    if host in {"0.0.0.0", "::"}:
        host = request.url.hostname or "localhost"

    default_port = 443 if scheme == "wss" else 80
    netloc = (
        host if settings.api_port == default_port else f"{host}:{settings.api_port}"
    )
    return f"{scheme}://{netloc}/jobs/ws/{{job_id}}"
