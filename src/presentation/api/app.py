"""FastAPI entrypoint for App file storage actions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from application.app import get_app
from infrastructure.config import get_settings
from presentation.api.routes.auth import routes as auth_routes
from presentation.api.routes.system import routes as system_routes


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan side-effects cleanly."""
    app = get_app()
    app.start()
    try:
        yield
    finally:
        app.close()


def api() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(
        title=settings.name,
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Register API routes
    fastapi_app.include_router(auth_routes)
    fastapi_app.include_router(system_routes)

    return fastapi_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "presentation.api.app:api",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
