"""Job status API routes."""

from __future__ import annotations

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
    await websocket.accept()
    try:
        async with app.database.connection() as conn:
            query = sql.SQL("LISTEN {channel}").format(
                channel=sql.Identifier(app.settings.outbox.output_channel)
            )
            await conn.execute(query)
        
            async for notification in conn.notifies():
                try:
                    data = json.loads(notification.payload)
                    obj = JobStatusResponse.model_validate(data).model_dump()
                    if data.get("id") == job_id:
                        await websocket.send_json(obj)
                        
                        # Optimization: If the job reaches a terminal state, gracefully close down
                        if data.get("status") in ["done", "failed"]:
                            await websocket.close(code=1000, reason="Job completed")
                            break
                            
                except (json.JSONDecodeError, KeyError):
                    continue
    except WebSocketDisconnect:
        pass
