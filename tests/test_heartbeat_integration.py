from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator

import pytest
import uvicorn
import websockets
from httpx import ASGITransport, AsyncClient

from application.app import App, get_app
from domain.event import Heartbeat
from domain.value import JobStatus
from infrastructure.config import Settings
from presentation.api.app import api


@pytest.fixture()
async def app(settings: Settings) -> AsyncIterator[App]:
    app = App.create(settings)
    await clear_outbox(app)
    try:
        yield app
    finally:
        await clear_outbox(app)
        await app.database.close()


async def test_request_heartbeat_persists_pending_job(app: App) -> None:
    job = await app.request_heartbeat(beats=5, interval=0.001)

    loaded = await app.get_job_status(job.id)

    assert loaded.id == job.id
    assert loaded.status == JobStatus.PENDING
    assert loaded.topic == Heartbeat.topic
    assert loaded.kind == Heartbeat.kind
    assert loaded.payload == {"beats": 5, "interval": 0.001}


async def test_request_heartbeat_clamps_beats_and_uses_default_interval(
    app: App,
) -> None:
    job = await app.request_heartbeat(beats=999)

    loaded = await app.get_job_status(job.id)

    assert loaded.payload == {
        "beats": app.settings.heartbeat.max_beats,
        "interval": app.settings.heartbeat.interval,
    }


async def test_runner_processes_pending_heartbeat_job_to_done(app: App) -> None:
    job = await app.request_heartbeat(beats=2, interval=0.001)

    await app.runner.poll()
    loaded = await app.get_job_status(job.id)

    assert loaded.status == JobStatus.DONE
    assert loaded.attempts == 1
    assert loaded.done_at is not None
    assert loaded.locked_at is None


async def test_asyncpg_unit_of_work_rolls_back_uncommitted_outbox_job(
    app: App,
) -> None:
    async with app.uow() as uow:
        job = await uow.outbox.append(
            Heartbeat.topic,
            Heartbeat.kind,
            {"beats": 1, "interval": 0.001},
            Heartbeat.version,
        )

    async with app.uow() as uow:
        loaded = await uow.outbox.get(job.id)

    assert loaded is None


async def test_api_heartbeat_route_uses_real_app_and_database(app: App) -> None:
    fastapi_app = api()
    fastapi_app.dependency_overrides[get_app] = lambda: app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/jobs/heartbeat",
            json={"beats": 1, "interval": 0.001},
        )

        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]

        status = await client.get(f"/jobs/{job_id}")

    assert status.status_code == 202
    assert status.json()["status"] == JobStatus.PENDING.value
    assert status.json()["payload"] == {"beats": 1, "interval": 0.001}


async def test_job_websocket_sends_current_terminal_status(app: App) -> None:
    job = await app.request_heartbeat(beats=1, interval=0.001)
    await app.runner.poll()

    fastapi_app = api()
    fastapi_app.dependency_overrides[get_app] = lambda: app
    server, port, task = await start_server(fastapi_app)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/jobs/ws/{job.id}") as ws:
            message = await asyncio.wait_for(ws.recv(), timeout=3)
    finally:
        server.should_exit = True
        await task

    payload = json.loads(message)
    assert payload["id"] == job.id
    assert payload["status"] == JobStatus.DONE.value


async def clear_outbox(app: App) -> None:
    async with app.database.connection() as conn:
        await conn.execute("DELETE FROM outbox")


async def start_server(fastapi_app) -> tuple[uvicorn.Server, int, asyncio.Task[None]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]

    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        lifespan="off",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))

    for _ in range(50):
        if server.started:
            return server, port, task
        await asyncio.sleep(0.01)

    server.should_exit = True
    await task
    raise RuntimeError("uvicorn test server did not start")
