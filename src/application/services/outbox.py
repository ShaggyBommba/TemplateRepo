from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from typing import Any

from prometheus_client import Counter, Histogram

from application.adapters.core import Dispatcher, Handler, UnitOfWork
from domain.event import Event, EventKey
from domain.value import JobStatus

logger = logging.getLogger(__name__)

outbox_jobs = Counter(
    "outbox_jobs_total",
    "Outbox jobs processed by the runner, labelled by terminal result.",
    ["topic", "kind", "result"],
)
outbox_dispatch_seconds = Histogram(
    "outbox_dispatch_seconds",
    "Time spent dispatching one outbox job to its handler.",
    ["topic", "kind"],
)


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
            async with self.factory() as uow:
                jobs = await uow.outbox.claim(
                    cls.topic,
                    cls.kind,
                    cls.version,
                    self.limit,
                )
                await uow.commit()

            if jobs:
                logger.info(
                    "Claimed %s outbox job(s) for topic=%s kind=%s version=%s",
                    len(jobs),
                    cls.topic.value,
                    cls.kind.value,
                    cls.version,
                )

            for job in jobs:
                topic = job.topic.value
                kind = job.kind.value
                try:
                    logger.info(
                        "Dispatching outbox job id=%s topic=%s kind=%s attempt=%s",
                        job.id,
                        topic,
                        kind,
                        job.attempts,
                    )
                    with outbox_dispatch_seconds.labels(topic, kind).time():
                        await self.dispatcher.dispatch(job.to_event())
                except Exception as exc:
                    outbox_jobs.labels(topic, kind, "failed").inc()
                    logger.exception(
                        "Outbox job failed id=%s topic=%s kind=%s retry=%s",
                        job.id,
                        topic,
                        kind,
                        True,
                    )
                    async with self.factory() as uow:
                        await uow.outbox.mark(
                            job.id,
                            JobStatus.PENDING,
                            str(exc),
                            retry=True,
                        )
                        await uow.commit()
                else:
                    outbox_jobs.labels(topic, kind, "done").inc()
                    logger.info(
                        "Outbox job completed id=%s topic=%s kind=%s",
                        job.id,
                        topic,
                        kind,
                    )
                    async with self.factory() as uow:
                        await uow.outbox.mark(job.id, JobStatus.DONE)
                        await uow.commit()

    async def run(self, interval: float = 1.0) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(interval)


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
