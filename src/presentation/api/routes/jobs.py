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
from psycopg import sql
import json
from fastapi import WebSocket, WebSocketDisconnect

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
def heartbeat(
    request: HeartbeatRequest,
    app: App = Depends(get_app),
) -> HeartbeatAccepted:
    job = app.request_heartbeat(request.beats, request.interval)
    return HeartbeatAccepted.from_domain(job)


@routes.get("/{job_id}", response_model=JobStatusResponse)
def get(
    job_id: str,
    response: Response,
    app: App = Depends(get_app),
) -> JobStatusResponse:
    try:
        job = app.get_job_status(job_id)
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
) -> None:
    """
    Listens natively to the Postgres outbox channel and filters updates 
    for a specific job_id over a persistent WebSocket connection.
    """
    terminal = {JobStatus.DONE, JobStatus.FAILED}
    await websocket.accept()
    try:
        async with app.database.connection() as conn:
            query = sql.SQL("LISTEN {channel}").format(
                channel=sql.Identifier(app.settings.outbox.output_channel)
            )
            await conn.execute(query)
            await conn.commit()

            # Send the current status first so clients that connect after a
            # notification (or after the job already finished) still see state.
            # LISTEN is registered above, so updates between this snapshot and
            # the stream below are buffered, not lost.
            try:
                job = await asyncio.to_thread(app.get_job_status, job_id)
            except JobNotFound:
                job = None
            if job is not None:
                await websocket.send_json(
                    JobStatusResponse.from_domain(job).model_dump(mode="json")
                )
                if job.status in terminal:
                    await websocket.close(code=1000, reason="Job completed")
                    return

            async for notification in conn.notifies():
                try:
                    data = json.loads(notification.payload)
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
    except WebSocketDisconnect:
        pass
