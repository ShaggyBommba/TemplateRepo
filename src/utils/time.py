from datetime import UTC, datetime


def now() -> datetime:
    """Return the timestamp used for row defaults."""
    return datetime.now(UTC)


def utc(timestamp: datetime) -> datetime:
    """Return a timezone-aware UTC timestamp."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
