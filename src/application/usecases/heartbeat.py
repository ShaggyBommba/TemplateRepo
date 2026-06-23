"""Heartbeat demo-job use cases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.adapters.core import UnitOfWork
from domain.entity import OutboxJob
from domain.event import Heartbeat


class RequestHeartbeatUseCase:
    """Enqueue one heartbeat job for the worker to process."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        default_beats: int,
        default_interval: float,
        max_beats: int,
    ) -> None:
        self.uow_factory = uow_factory
        self.default_beats = default_beats
        self.default_interval = default_interval
        self.max_beats = max_beats

    def __call__(
        self,
        beats: int | None = None,
        interval: float | None = None,
    ) -> OutboxJob[dict[str, Any]]:
        payload = {
            "beats": min(beats or self.default_beats, self.max_beats),
            "interval": interval or self.default_interval,
        }

        with self.uow_factory() as uow:
            job = uow.outbox.append(
                Heartbeat.topic,
                Heartbeat.kind,
                payload,
                Heartbeat.version,
            )
            uow.commit()

        return job
