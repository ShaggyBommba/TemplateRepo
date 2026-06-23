from __future__ import annotations

from typing import Any

from application.usecases.heartbeat import RequestHeartbeatUseCase
from domain.entity import OutboxJob
from domain.value import EventKind, EventTopic


class FakeOutbox:
    """In-memory outbox that records appended jobs."""

    def __init__(self) -> None:
        self.jobs: list[OutboxJob[dict[str, Any]]] = []

    def append(
        self,
        topic: EventTopic,
        kind: EventKind,
        payload: dict[str, Any],
        version: int = 1,
        max_attempts: int | None = None,
        idempotency_key: str | None = None,
    ) -> OutboxJob[dict[str, Any]]:
        job = OutboxJob(
            id=f"job-{len(self.jobs) + 1}",
            trace_id="trace",
            topic=topic,
            kind=kind,
            version=version,
            payload=payload,
            max_attempts=3,
        )
        self.jobs.append(job)
        return job


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.outbox = FakeOutbox()
        self.job = self.outbox
        self.committed = False

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


def make_usecase(uow: FakeUnitOfWork, *, max_beats: int = 60) -> RequestHeartbeatUseCase:
    return RequestHeartbeatUseCase(
        lambda: uow,
        default_beats=3,
        default_interval=1.0,
        max_beats=max_beats,
    )


def test_request_heartbeat_usecase_appends_job_and_commits() -> None:
    # Arrange
    uow = FakeUnitOfWork()
    usecase = make_usecase(uow)

    # Act
    job = usecase(beats=5, interval=2.0)

    # Assert
    assert uow.committed
    assert len(uow.outbox.jobs) == 1
    appended = uow.outbox.jobs[0]
    assert appended.id == job.id
    assert appended.topic == EventTopic.HEARTBEAT
    assert appended.kind == EventKind.BEAT
    assert appended.payload == {"beats": 5, "interval": 2.0}


def test_request_heartbeat_usecase_uses_defaults_when_unset() -> None:
    # Arrange
    uow = FakeUnitOfWork()
    usecase = make_usecase(uow)

    # Act
    usecase()

    # Assert
    assert uow.outbox.jobs[0].payload == {"beats": 3, "interval": 1.0}


def test_request_heartbeat_usecase_clamps_beats_to_max() -> None:
    # Arrange
    uow = FakeUnitOfWork()
    usecase = make_usecase(uow, max_beats=10)

    # Act
    usecase(beats=999, interval=1.0)

    # Assert
    assert uow.outbox.jobs[0].payload["beats"] == 10
