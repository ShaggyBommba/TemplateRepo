"""Job status API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from application.app import App, get_app
from application.error import JobNotFound
from domain.entity import OutboxJob
from domain.value import JobStatus
import json
from fastapi import WebSocket, WebSocketDisconnect
from application.dto import Principal
from presentation.api.dependencies import require

routes = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStatusResponse(BaseModel):
    id: str
    status: str = Field(
        examples=["pending", "processing", "completed", "failed"],
    )
    payload: dict[str, object] | None = None
    error: str | None = None
    last_error: str | None = None
    attempts: int | None = None
    max_attempts: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, job: OutboxJob[dict[str, object]]) -> JobStatusResponse:
        return cls(
            id=job.id,
            status=job.status.value,
            payload=job.payload,
            error=job.last_error,
            last_error=job.last_error,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            started_at=job.locked_at,
            finished_at=job.done_at,
        )


class HeartbeatRequest(BaseModel):
    beats: int | None = Field(default=None, ge=1)
    interval: float | None = Field(default=None, gt=0)


class HeartbeatAccepted(BaseModel):
    job_id: str

    @classmethod
    def from_domain(cls, job: OutboxJob[dict[str, object]]) -> HeartbeatAccepted:
        return cls(job_id=job.id)


@routes.post(
    "/heartbeat",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=HeartbeatAccepted,
)
async def heartbeat(
    request: HeartbeatRequest,
    app: App = Depends(get_app),
    _: Principal = Depends(require("users:read")),
) -> HeartbeatAccepted:
    job = await app.request_heartbeat(request.beats, request.interval)
    return HeartbeatAccepted.from_domain(job)


@routes.get("/{job_id}", response_model=JobStatusResponse)
async def get(
    job_id: str,
    response: Response,
    app: App = Depends(get_app),
    _: Principal = Depends(require("users:read")),
) -> JobStatusResponse:
    try:
        job = await app.get_job_status(job_id)
    except JobNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    response.status_code = (
        status.HTTP_202_ACCEPTED
        if job.status in {JobStatus.PENDING, JobStatus.RUNNING}
        else status.HTTP_200_OK
    )
    return JobStatusResponse.from_domain(job)


@routes.websocket("/ws/{job_id}")
async def stream(
    websocket: WebSocket,
    job_id: str,
    app: App = Depends(get_app),
    _: Principal = Depends(require("users:read")),
) -> None:
    """
    Listens natively to the Postgres outbox channel and filters updates
    for a specific job_id over a persistent WebSocket connection.
    """
    terminal = {JobStatus.DONE, JobStatus.FAILED}
    await websocket.accept()
    try:
        async with app.database.connection() as conn:
            queue: asyncio.Queue[str] = asyncio.Queue()
            channel = app.settings.outbox.output_channel

            def listener(
                connection: object,
                pid: int,
                channel: str,
                payload: str,
            ) -> None:
                queue.put_nowait(payload)

            await conn.add_listener(channel, listener)
            try:
                try:
                    job = await app.get_job_status(job_id)
                except JobNotFound:
                    job = None
                if job is not None:
                    await websocket.send_json(
                        JobStatusResponse.from_domain(job).model_dump(mode="json")
                    )
                    if job.status in terminal:
                        await websocket.close(code=1000, reason="Job completed")
                        return

                while True:
                    payload = await queue.get()
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if data.get("id") != job_id:
                        continue

                    update = OutboxJob.model_validate(data)
                    await websocket.send_json(
                        JobStatusResponse.from_domain(update).model_dump(mode="json")
                    )

                    # Optimization: once a job reaches a terminal state, close cleanly.
                    if update.status in terminal:
                        await websocket.close(code=1000, reason="Job completed")
                        break
            finally:
                await conn.remove_listener(channel, listener)
    except WebSocketDisconnect:
        pass
