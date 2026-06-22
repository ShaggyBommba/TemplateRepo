"""FastAPI entrypoint for the HTMX template surface."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from application.app import get_app
from infrastructure.config import get_settings
from presentation.htmx.features.auth.routes import routes as auth_routes
from presentation.htmx.features.home.routes import routes as home_routes
from presentation.htmx.features.system.routes import routes as system_routes

FEATURE_DIR = Path(__file__).resolve().parent / "features"
templates = Jinja2Templates(directory=str(FEATURE_DIR))


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan side-effects cleanly."""
    app = get_app()
    await app.start()
    try:
        yield
    finally:
        await app.close()


def api() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(
        title=settings.name,
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    fastapi_app.state.templates = templates

    fastapi_app.include_router(auth_routes)
    fastapi_app.include_router(home_routes)
    fastapi_app.include_router(system_routes)

    return fastapi_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "presentation.htmx.app:api",
        factory=True,
        host=settings.htmx_host,
        port=settings.htmx_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
