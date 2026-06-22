from __future__ import annotations

from asyncio import sleep
from functools import lru_cache
from logging import getLogger
from typing import Callable

from application.services.outbox import EventDispatcher, OutboxRunner
from application.usecases.auth import Authorize
from infrastructure.auth.keycloak import KeycloakVerifier
from infrastructure.config import Settings, get_settings
from infrastructure.observability.logger import LoggingService
from infrastructure.persistence.database import SqlDatabase
from infrastructure.persistence.uow import SqlUnitOfWork

logger = getLogger(__name__)


class App:
    """Application facade used by entrypoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        logger.info(
            "Initializing application name=%s version=%s env=%s",
            settings.name,
            settings.version,
            settings.env,
        )
        self.database = SqlDatabase(settings.database)
        self.database.create_all()
        self.uow_factory: Callable[[], SqlUnitOfWork] = lambda: SqlUnitOfWork(
            self.database.sessions(),
            self.settings.outbox,
        )
        self.dispatcher = EventDispatcher()
        self.authorize = Authorize(KeycloakVerifier(settings.keycloak))

        self.runner = OutboxRunner(
            dispatcher=self.dispatcher,
            events=(),
            limit=self.settings.worker_batch_limit,
            factory=self.uow_factory,
        )
        logger.info(
            "Application initialized database_provider=%s worker_batch_limit=%s",
            settings.database.provider,
            settings.worker_batch_limit,
        )

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def version(self) -> str:
        return self.settings.version

    @property
    def healthy(self) -> bool:
        return True

    def start(self) -> None:
        """Start the application."""
        logger.info(f"Starting {self.name} v{self.version}...")

    def close(self) -> None:
        """Close the application."""
        logger.info(f"Closing {self.name}...")

    async def daemon(self) -> None:
        """Run background tasks."""
        while True:
            logger.debug("Polling runner for background tasks...")
            await self.runner.poll()
            await sleep(self.settings.worker_poll_interval)


@lru_cache(maxsize=1)
def get_app() -> App:
    """Build the application from concrete infrastructure adapters."""
    settings = get_settings()
    LoggingService.setup(settings.logging)
    return App(settings=settings)
