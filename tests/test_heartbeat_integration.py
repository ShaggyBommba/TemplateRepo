from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from application.app import App, get_app
from domain.event import Heartbeat
from domain.value import JobStatus
from infrastructure.config import Settings
from presentation.api.app import api


@pytest.fixture()
def app(settings: Settings) -> Iterator[App]:
    app = App.create(settings)
    clear_outbox(app)
    try:
        yield app
    finally:
        clear_outbox(app)
        app.database.close()


def test_request_heartbeat_persists_pending_job(app: App) -> None:
    job = app.request_heartbeat(beats=5, interval=0.001)

    loaded = app.get_job_status(job.id)

    assert loaded.id == job.id
    assert loaded.status == JobStatus.PENDING
    assert loaded.topic == Heartbeat.topic
    assert loaded.kind == Heartbeat.kind
    assert loaded.payload == {"beats": 5, "interval": 0.001}


def test_request_heartbeat_clamps_beats_and_uses_default_interval(app: App) -> None:
    job = app.request_heartbeat(beats=999)

    loaded = app.get_job_status(job.id)

    assert loaded.payload == {
        "beats": app.settings.heartbeat.max_beats,
        "interval": app.settings.heartbeat.interval,
    }


async def test_runner_processes_pending_heartbeat_job_to_done(app: App) -> None:
    job = app.request_heartbeat(beats=2, interval=0.001)

    await app.runner.poll()
    loaded = app.get_job_status(job.id)

    assert loaded.status == JobStatus.DONE
    assert loaded.attempts == 1
    assert loaded.done_at is not None
    assert loaded.locked_at is None


def test_sql_unit_of_work_rolls_back_uncommitted_outbox_job(app: App) -> None:
    with app.uow() as uow:
        job = uow.outbox.append(
            Heartbeat.topic,
            Heartbeat.kind,
            {"beats": 1, "interval": 0.001},
            Heartbeat.version,
        )

    with app.uow() as uow:
        loaded = uow.outbox.get(job.id)

    assert loaded is None


def test_api_heartbeat_route_uses_real_app_and_database(app: App) -> None:
    fastapi_app = api()
    fastapi_app.dependency_overrides[get_app] = lambda: app
    client = TestClient(fastapi_app)

    accepted = client.post(
        "/jobs/heartbeat",
        json={"beats": 1, "interval": 0.001},
    )

    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]

    status = client.get(f"/jobs/{job_id}")

    assert status.status_code == 202
    assert status.json()["status"] == JobStatus.PENDING.value
    assert status.json()["payload"] == {"beats": 1, "interval": 0.001}


def clear_outbox(app: App) -> None:
    with app.database.engine().begin() as conn:
        conn.execute(text("DELETE FROM outbox"))
