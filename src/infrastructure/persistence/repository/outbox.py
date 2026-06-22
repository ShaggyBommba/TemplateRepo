from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from domain.entity import OutboxJob
from domain.value import EventKind, EventTopic, JobStatus
from infrastructure.config import OutboxSettings
from infrastructure.persistence.models import OutboxRow
from utils.time import now

logger = logging.getLogger(__name__)


class OutboxRepo:
    """SQL-backed outbox repository."""

    def __init__(
        self,
        session: Session,
        settings: OutboxSettings,
    ) -> None:
        self.session = session
        self.settings = settings



    def notify(self, job: OutboxJob[dict[str, Any]]) -> None:
        """Notify listeners of outbox job status changes."""
        try:
            self.session.execute(
                select(func.pg_notify(self.settings.output_channel, job.model_dump_json()))
            )
            self.session.flush()
            logger.debug(
                "Sent outbox notification for job id=%s status=%s",
                job.id,
                job.status,
            )
        except Exception as exc:
            logger.warning(
                "Failed to send outbox notification for job id=%s status=%s: %s",
                job.id,
                job.status,
                exc,
            )

    def append(
        self,
        topic: EventTopic,
        kind: EventKind,
        payload: dict[str, Any],
        version: int = 1,
        max_attempts: int = 3,
        idempotency_key: str | None = None,
    ) -> OutboxJob[dict[str, Any]]:
        max_attempts = self.settings.default_max_attempts or max_attempts

        row = OutboxRow(
            id=str(uuid4()),
            trace_id=str(uuid4()),
            idempotency_key=idempotency_key,
            topic=topic.value,
            kind=kind.value,
            version=version,
            payload=payload,
            status=JobStatus.PENDING.value,
            attempts=0,
            max_attempts=max_attempts,
            available_at=now(),
        )
        self.session.add(row)
        self.session.flush()
        self.notify(row.to_domain())

        logger.info(
            "Appended outbox job id=%s topic=%s kind=%s version=%s idempotency_key=%s",
            row.id,
            topic.value,
            kind.value,
            version,
            idempotency_key,
        )
        return row.to_domain()

    def get(self, job_id: str) -> OutboxJob[dict[str, Any]] | None:
        row = self.session.get(OutboxRow, job_id)
        if row is None:
            logger.debug("Outbox job not found id=%s", job_id)
            return None
        return row.to_domain()

    def due(
        self,
        topic: EventTopic,
        kind: EventKind,
        version: int,
        limit: int,
    ) -> list[OutboxJob[dict[str, Any]]]:
        rows = self.session.scalars(
            select(OutboxRow)
            .where(
                OutboxRow.topic == topic.value,
                OutboxRow.kind == kind.value,
                OutboxRow.version == version,
                OutboxRow.status == JobStatus.PENDING.value,
                OutboxRow.available_at <= now(),
            )
            .order_by(OutboxRow.available_at, OutboxRow.id)
            .limit(limit)
        ).all()
        if rows:
            logger.debug(
                "Read %s due outbox job(s) topic=%s kind=%s version=%s",
                len(rows),
                topic.value,
                kind.value,
                version,
            )
        return [row.to_domain() for row in rows]

    def claim(
        self,
        topic: EventTopic,
        kind: EventKind,
        version: int,
        limit: int,
    ) -> list[OutboxJob[dict[str, Any]]]:
        cutoff = now() - timedelta(seconds=self.settings.claim_timeout_seconds)
        rows = self.session.scalars(
            select(OutboxRow)
            .where(
                OutboxRow.topic == topic.value,
                OutboxRow.kind == kind.value,
                OutboxRow.version == version,
                OutboxRow.available_at <= now(),
                or_(
                    OutboxRow.status == JobStatus.PENDING.value,
                    and_(
                        OutboxRow.status == JobStatus.RUNNING.value,
                        OutboxRow.locked_at <= cutoff,
                    ),
                ),
            )
            .order_by(OutboxRow.available_at, OutboxRow.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()

        locked_at = now()
        for row in rows:
            row.status = JobStatus.RUNNING.value
            row.locked_at = locked_at
            row.attempts += 1
            self.session.flush()
            self.notify(row.to_domain())

        if rows:
            logger.info(
                "Claimed %s outbox row(s) topic=%s kind=%s version=%s",
                len(rows),
                topic.value,
                kind.value,
                version,
            )
        return [row.to_domain() for row in rows]

    def mark(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        retry: bool = True,
    ) -> None:
        row = self.session.get(OutboxRow, job_id)
        if row is None:
            logger.warning(
                "Cannot mark missing outbox job id=%s status=%s", job_id, status
            )
            return

        status = JobStatus(status)
        if status == JobStatus.DONE:
            row.status = JobStatus.DONE.value
            row.done_at = now()
            row.locked_at = None
            row.last_error = error
            logger.info("Marked outbox job done id=%s", job_id)
            self.session.flush()
            self.notify(row.to_domain())
            return

        if status == JobStatus.FAILED or not retry or row.attempts >= row.max_attempts:
            row.status = JobStatus.FAILED.value
            row.locked_at = None
            row.last_error = error
            logger.error(
                "Marked outbox job failed id=%s attempts=%s max_attempts=%s error=%s",
                job_id,
                row.attempts,
                row.max_attempts,
                error,
            )
            self.session.flush()
            self.notify(row.to_domain())
            return

        row.status = JobStatus.PENDING.value
        row.available_at = now()
        row.locked_at = None
        row.last_error = error
        logger.warning(
            "Requeued outbox job id=%s attempts=%s max_attempts=%s error=%s",
            job_id,
            row.attempts,
            row.max_attempts,
            error,
        )
        self.session.flush()
        self.notify(row.to_domain())
