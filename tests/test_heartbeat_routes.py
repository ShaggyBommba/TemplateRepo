from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.app import get_app
from domain.entity import OutboxJob
from domain.value import EventKind, EventTopic
from presentation.api.routes.jobs import HeartbeatRequest, heartbeat, routes


class FakeApp:
    """Minimal app surface used by the heartbeat route."""

    def __init__(self, job: OutboxJob[dict[str, object]]) -> None:
        self.job = job
        self.calls: list[tuple[int | None, float | None]] = []

    def request_heartbeat(
        self,
        beats: int | None = None,
        interval: float | None = None,
    ) -> OutboxJob[dict[str, object]]:
        self.calls.append((beats, interval))
        return self.job


def test_heartbeat_route_enqueues_job_and_returns_id() -> None:
    # Arrange
    job = make_job(payload={"beats": 2, "interval": 0.5})
    app = FakeApp(job)

    # Act
    response = heartbeat(HeartbeatRequest(beats=2, interval=0.5), app=app)

    # Assert
    assert response.job_id == "hb-1"
    assert app.calls == [(2, 0.5)]


def test_heartbeat_route_rejects_missing_body() -> None:
    # Arrange
    app = FakeApp(make_job())
    api = FastAPI()
    api.dependency_overrides[get_app] = lambda: app
    api.include_router(routes)
    client = TestClient(api)

    # Act
    response = client.post("/jobs/heartbeat")

    # Assert
    assert response.status_code == 422
    assert app.calls == []


def test_heartbeat_route_uses_defaults_when_body_is_empty() -> None:
    # Arrange
    app = FakeApp(make_job())
    api = FastAPI()
    api.dependency_overrides[get_app] = lambda: app
    api.include_router(routes)
    client = TestClient(api)

    # Act
    response = client.post("/jobs/heartbeat", json={})

    # Assert
    assert response.status_code == 202
    assert response.json() == {"job_id": "hb-1"}
    assert app.calls == [(None, None)]


def make_job(
    *,
    payload: dict[str, object] | None = None,
) -> OutboxJob[dict[str, object]]:
    return OutboxJob(
        id="hb-1",
        trace_id="trace",
        topic=EventTopic.HEARTBEAT,
        kind=EventKind.BEAT,
        payload=payload or {"beats": 1, "interval": 0.1},
        max_attempts=3,
    )
