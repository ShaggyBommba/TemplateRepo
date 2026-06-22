from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from domain.event import Event, REGISTRY
from domain.value import EventKind, EventTopic, JobStatus

PayloadT = TypeVar("PayloadT")


class DomainModel(BaseModel):
    """Base class for immutable domain models."""

    model_config = ConfigDict(frozen=True)


class OutboxJob(DomainModel, Generic[PayloadT]):
    """Durable queued work item loaded from the outbox."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str
    idempotency_key: str | None = None
    topic: EventTopic
    kind: EventKind
    payload: PayloadT
    max_attempts: int
    version: int = 1
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    available_at: datetime | None = None
    locked_at: datetime | None = None
    done_at: datetime | None = None
    last_error: str | None = None

    @classmethod
    def from_event(
        cls,
        event: Event[PayloadT],
        *,
        max_attempts: int = 3,
        available_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> OutboxJob[PayloadT]:
        return cls(
            id=event.id,
            trace_id=event.trace_id,
            idempotency_key=idempotency_key,
            topic=event.topic,
            kind=event.kind,
            version=event.version,
            payload=event.payload,
            max_attempts=max_attempts,
            available_at=available_at,
        )

    def to_event(self) -> Event[PayloadT]:
        """Convert this job back into an event."""
        key = (self.topic, self.kind, self.version)
        cls = REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"No event class registered for {key}")
        return cls(payload=self.payload, id=self.id, trace_id=self.trace_id)

