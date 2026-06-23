from enum import StrEnum


class JobStatus(StrEnum):
    """Durable outbox job state."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class EventTopic(StrEnum):
    """Event topic, used for categorization and routing."""

    HEARTBEAT = "heartbeat"


class EventKind(StrEnum):
    """Event kind, used for categorization and routing."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    PARSED = "parsed"
    BEAT = "beat"
