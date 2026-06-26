from __future__ import annotations

import time
from logging import getLogger

from fastapi import FastAPI
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
    start_http_server,
)
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from infrastructure.config import MetricsSettings

logger = getLogger(__name__)

http_requests = Counter(
    "http_requests_total",
    "HTTP requests handled, labelled by method, route template, and status.",
    ["method", "path", "status"],
)
http_request_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, labelled by method and route template.",
    ["method", "path"],
)


class PrometheusMiddleware:
    """Record RED request metrics using the matched route template as the label.

    Labelling by route template (`/jobs/{job_id}`) rather than the raw path keeps
    metric cardinality bounded; unmatched paths collapse to one series.
    """

    def __init__(self, app: ASGIApp, metrics_path: str) -> None:
        self.app = app
        self.metrics_path = metrics_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == self.metrics_path:
            await self.app(scope, receive, send)
            return

        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, capture)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or "__unmatched__"
            method = scope["method"]
            http_requests.labels(method, path, str(status)).inc()
            http_request_seconds.labels(method, path).observe(
                time.perf_counter() - start
            )


class MetricsService:
    """Exposes Prometheus metrics for HTTP apps and the worker process.

    Business metrics defined with prometheus_client register against the
    default registry, so every exposition surface here publishes them
    without extra wiring.
    """

    @staticmethod
    def expose(app: FastAPI, settings: MetricsSettings) -> None:
        """Attach RED request metrics and a scrape endpoint to a FastAPI app."""
        if not settings.enabled:
            return
        app.add_middleware(PrometheusMiddleware, metrics_path=settings.path)
        app.add_api_route(
            settings.path,
            MetricsService.render,
            methods=["GET"],
            include_in_schema=False,
        )
        logger.info("Metrics endpoint enabled at %s", settings.path)

    @staticmethod
    def render() -> Response:
        """Render the default Prometheus registry for scraping."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @staticmethod
    def serve(settings: MetricsSettings) -> None:
        """Start a standalone exposition server for the non-HTTP worker."""
        if not settings.enabled:
            return
        start_http_server(settings.worker_port)
        logger.info("Metrics server started on port %s", settings.worker_port)
