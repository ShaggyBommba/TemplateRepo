from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, TypeVar
import uuid
from domain.value import EventTopic, EventKind


PayloadT = TypeVar("PayloadT")
EventKey = tuple[EventTopic, EventKind, int]


# Global registry for event classes, keyed by (topic, kind, version).
REGISTRY: dict[EventKey, type[Event[Any]]] = {}


def register(cls: type[Event[Any]]) -> type[Event[Any]]:
    key = (cls.topic, cls.kind, cls.version)

    if key in REGISTRY:
        existing = REGISTRY[key]
        raise ValueError(
            f"Duplicate event registration for {key}: "
            f"{existing.__name__} and {cls.__name__}"
        )

    REGISTRY[key] = cls
    return cls


@dataclass(frozen=True, slots=True)
class Event(Generic[PayloadT]):
    """Generic event emitted by the application, used for outbox jobs and other purposes."""

    topic: ClassVar[EventTopic]
    kind: ClassVar[EventKind]
    version: ClassVar[int] = 1

    payload: PayloadT
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """Return the unique key for this event, used for idempotency."""
        return f"{self.topic.value}:{self.kind.value}:{self.version}:{self.id}"
