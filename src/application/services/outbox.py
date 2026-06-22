from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from typing import Any

from application.adapters.core import Dispatcher, Handler, UnitOfWork
from domain.event import Event, EventKey
from domain.value import JobStatus

logger = logging.getLogger(__name__)


class OutboxRunner:
    """Claim due outbox jobs and dispatch their events once."""

    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        dispatcher: Dispatcher,
        events: Iterable[type[Event[Any]]],
        limit: int,
    ) -> None:
        self.factory = factory
        self.dispatcher = dispatcher
        self.events = tuple(events)
        self.limit = limit

    async def poll(self) -> None:
        for cls in self.events:
            logger.debug(
                "Polling outbox for event topic=%s kind=%s version=%s limit=%s",
                cls.topic.value,
                cls.kind.value,
                cls.version,
                self.limit,
            )
            with self.factory() as uow:
                jobs = uow.outbox.claim(
                    cls.topic,
                    cls.kind,
                    cls.version,
                    self.limit,
                )
                uow.commit()

            if jobs:
                logger.info(
                    "Claimed %s outbox job(s) for topic=%s kind=%s version=%s",
                    len(jobs),
                    cls.topic.value,
                    cls.kind.value,
                    cls.version,
                )

            for job in jobs:
                try:
                    logger.info(
                        "Dispatching outbox job id=%s topic=%s kind=%s attempt=%s",
                        job.id,
                        job.topic.value,
                        job.kind.value,
                        job.attempts,
                    )
                    await self.dispatcher.dispatch(job.to_event())
                except Exception as exc:
                    logger.exception(
                        "Outbox job failed id=%s topic=%s kind=%s retry=%s",
                        job.id,
                        job.topic.value,
                        job.kind.value,
                        True,
                    )
                    with self.factory() as uow:
                        uow.outbox.mark(
                            job.id,
                            JobStatus.PENDING,
                            str(exc),
                            retry=True,
                        )
                        uow.commit()
                else:
                    logger.info(
                        "Outbox job completed id=%s topic=%s kind=%s",
                        job.id,
                        job.topic.value,
                        job.kind.value,
                    )
                    with self.factory() as uow:
                        uow.outbox.mark(job.id, JobStatus.DONE)
                        uow.commit()

    async def run(self, interval_seconds: float = 1.0) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(interval_seconds)


class EventDispatcher:
    """Dispatch events to registered async handlers."""

    def __init__(self) -> None:
        self.handlers: dict[EventKey, Handler[Any]] = {}

    def register[PayloadT](
        self,
        cls: type[Event[PayloadT]],
        handler: Handler[PayloadT],
    ) -> None:
        key = (cls.topic, cls.kind, cls.version)
        if key in self.handlers:
            raise ValueError(f"Handler already registered for {key}")
        self.handlers[key] = handler
        logger.info(
            "Registered event handler topic=%s kind=%s version=%s handler=%s",
            cls.topic.value,
            cls.kind.value,
            cls.version,
            type(handler).__name__,
        )

    async def dispatch(self, event: Event[Any]) -> None:
        key = (event.topic, event.kind, event.version)
        handler = self.handlers.get(key)
        if handler is None:
            raise LookupError(f"No handler registered for {key}")
        logger.debug(
            "Dispatching event id=%s topic=%s kind=%s version=%s handler=%s",
            event.id,
            event.topic.value,
            event.kind.value,
            event.version,
            type(handler).__name__,
        )
        await handler(event)
