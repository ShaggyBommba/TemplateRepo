from __future__ import annotations

from asyncio import sleep
from functools import lru_cache
from logging import getLogger
from typing import Callable

from application.services.outbox import EventDispatcher, OutboxRunner
from application.usecases.auth import Authorize
from application.usecases.jobs import GetJobStatusUseCase
from infrastructure.auth.keycloak import KeycloakVerifier
from infrastructure.config import Settings, get_settings
from infrastructure.observability.logger import LoggingService
from infrastructure.persistence.database import SqlDatabase
from infrastructure.persistence.uow import SqlUnitOfWork
from dataclasses import dataclass
logger = getLogger(__name__)


@dataclass
class App:
    """Application facade used by entrypoints."""

    settings: Settings
    database: SqlDatabase
    dispatcher: EventDispatcher
    authorize: Authorize
    runner: OutboxRunner
    get_job_status: GetJobStatusUseCase


    @classmethod
    def create(cls, settings: Settings) -> App: 
        database = SqlDatabase(settings.database)
        database.create_all()
        dispatcher = EventDispatcher()
        authorize = Authorize(KeycloakVerifier(settings.keycloak))
        get_job_status = GetJobStatusUseCase(lambda: SqlUnitOfWork(
            database.sessions(),
            settings.outbox,
        ))
        runner = OutboxRunner(
            dispatcher=dispatcher,
            events=(),
            limit=settings.worker_batch_limit,
            factory=lambda: SqlUnitOfWork(
                database.sessions(),
                settings.outbox,
            ),
        )

        return cls(
            settings=settings,
            database=database,
            dispatcher=dispatcher,
            authorize=authorize,
            runner=runner,
            get_job_status=get_job_status,
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

    async def start(self) -> None:
        """Start the application."""
        logger.info(f"Starting {self.name} v{self.version}...")

    async def close(self) -> None:
        """Close the application."""
        logger.info(f"Closing {self.name}...")
        self.database.close()


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
    return App.create(settings=settings)
