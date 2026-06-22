"""System API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from application.app import App, get_app

routes = APIRouter(tags=["system"])


@routes.get("/health")
def health(app: App = Depends(get_app)) -> dict[str, bool]:
    return {"healthy": app.healthy}


@routes.get("/version")
def version(app: App = Depends(get_app)) -> dict[str, str]:
    return {"version": app.version}
