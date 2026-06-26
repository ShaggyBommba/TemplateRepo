"""Job-status use cases."""

from __future__ import annotations

from collections.abc import Callable

from application.adapters.core import UnitOfWork
from application.error import JobNotFound
from domain.entity import OutboxJob


class GetJobStatusUseCase:
    """Fetch job status from durable storage."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    async def __call__(self, job_id: str) -> OutboxJob[dict[str, object]]:
        async with self.uow_factory() as uow:
            job = await uow.job.get(job_id)
            if job is None:
                raise JobNotFound(job_id)
            return job
