from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, TypeVar, runtime_checkable

from application.dto import Principal
from domain.entity import OutboxJob
from domain.event import Event
from domain.value import EventKind, EventTopic, JobStatus

EntityT = TypeVar("EntityT")
SearchEntityT = TypeVar("SearchEntityT", contravariant=True)
SearchResultT = TypeVar("SearchResultT")


@runtime_checkable
class CrudRepo(Protocol[EntityT]):
    """Persists domain entities with basic CRUD operations."""

    async def add(self, entity: EntityT, /) -> EntityT:
        """Insert or update an entity by primary key (idempotent)."""
        ...

    async def get(self, entity_id: str, /) -> EntityT | None:
        """Read one entity by id."""
        ...

    async def list(self, *args, **kwargs: Any) -> list[EntityT]:
        """Read all entities."""
        ...

    async def remove(self, entity_id: str, /) -> EntityT | None:
        """Remove one entity by id. Return the removed entity or None if not found."""
        ...


@runtime_checkable
class JobRepo(Protocol):
    """Reads background job status by identifier."""

    async def get(self, job_id: str, /) -> OutboxJob | None:
        """Read one job by id."""
        ...


@runtime_checkable
class OutboxRepo(Protocol):
    """Persists durable queued work."""

    async def append(
        self,
        topic: EventTopic,
        kind: EventKind,
        payload: dict[str, Any],
        version: int = 1,
        max_attempts: int = 3,
        idempotency_key: str | None = None,
    ) -> OutboxJob:
        """Insert or revive one idempotent outbox job."""
        ...

    async def get(self, job_id: str, /) -> OutboxJob | None:
        """Read one job by id."""
        ...

    async def due(
        self, topic: EventTopic, kind: EventKind, version: int, limit: int
    ) -> list[OutboxJob]:
        """Read ready pending jobs without claiming them."""
        ...

    async def claim(
        self, topic: EventTopic, kind: EventKind, version: int, limit: int
    ) -> list[OutboxJob]:
        """Claim ready pending jobs for processing."""
        ...

    async def mark(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        retry: bool = True,
    ) -> None:
        """Move one claimed job to its next durable state."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Coordinates repositories that share one transactional session."""

    # REPOSITORIES
    job: JobRepo
    outbox: OutboxRepo

    async def __aenter__(self) -> UnitOfWork:
        """Open one transactional session and expose repositories."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Rollback uncommitted work and close the session."""
        ...

    async def commit(self) -> None:
        """Commit all staged repository changes atomically."""
        ...

    async def rollback(self) -> None:
        """Rollback all staged repository changes."""
        ...


@runtime_checkable
class TokenVerifier(Protocol):
    """Verifies bearer tokens from an identity provider."""

    def get(self, token: str, /) -> Principal | None:
        """Return a trusted caller, or None when the token is not trusted."""
        ...


@runtime_checkable
class Handler[PayloadT](Protocol):
    async def __call__(self, event: Event[PayloadT]) -> None: ...


@runtime_checkable
class Dispatcher(Protocol):
    def register[PayloadT](
        self,
        cls: type[Event[PayloadT]],
        handler: Handler[PayloadT],
    ) -> None: ...

    async def dispatch(self, event: Event[Any]) -> None: ...


@runtime_checkable
class Runner(Protocol):
    async def poll(self) -> None: ...
