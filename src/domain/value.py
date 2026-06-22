from enum import StrEnum


class JobStatus(StrEnum):
    """Durable outbox job state."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

class EventTopic(StrEnum):
    """Event topic, used for categorization and routing."""

    SCRAPE = "scrape"
    BILLING = "billing"


class EventKind(StrEnum):
    """Event kind, used for categorization and routing."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    PARSED = "parsed"
