from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

from asyncpg.pool import PoolConnectionProxy

from domain.entity import OutboxJob
from domain.value import EventKind, EventTopic, JobStatus
from infrastructure.config import OutboxSettings
from utils.time import now

logger = logging.getLogger(__name__)


class OutboxRepo:
    """asyncpg-backed outbox repository."""

    def __init__(
        self,
        conn: PoolConnectionProxy,
        settings: OutboxSettings,
    ) -> None:
        self.conn = conn
        self.settings = settings

    async def notify(self, job: OutboxJob[dict[str, Any]]) -> None:
        """Notify listeners of outbox job status changes."""
        try:
            await self.conn.execute(
                "SELECT pg_notify($1, $2)",
                self.settings.output_channel,
                job.model_dump_json(),
            )
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

    async def append(
        self,
        topic: EventTopic,
        kind: EventKind,
        payload: dict[str, Any],
        version: int = 1,
        max_attempts: int = 3,
        idempotency_key: str | None = None,
    ) -> OutboxJob[dict[str, Any]]:
        max_attempts = self.settings.default_max_attempts or max_attempts
        timestamp = now()

        row = await self.conn.fetchrow(
            """
            INSERT INTO outbox (
                id,
                trace_id,
                idempotency_key,
                topic,
                kind,
                version,
                payload,
                status,
                attempts,
                max_attempts,
                available_at,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, $9, $10, $11, $11)
            RETURNING *
            """,
            str(uuid4()),
            str(uuid4()),
            idempotency_key,
            topic.value,
            kind.value,
            version,
            payload,
            JobStatus.PENDING.value,
            max_attempts,
            timestamp,
            timestamp,
        )
        assert row is not None, "Failed to insert outbox job"
        job = OutboxJob.model_validate(dict(row))
        await self.notify(job)

        logger.info(
            "Appended outbox job id=%s topic=%s kind=%s version=%s idempotency_key=%s",
            job.id,
            topic.value,
            kind.value,
            version,
            idempotency_key,
        )
        return job

    async def get(self, job_id: str) -> OutboxJob[dict[str, Any]] | None:
        row = await self.conn.fetchrow(
            "SELECT * FROM outbox WHERE id = $1",
            job_id,
        )
        if row is None:
            logger.debug("Outbox job not found id=%s", job_id)
            return None
        return OutboxJob.model_validate(dict(row))

    async def due(
        self,
        topic: EventTopic,
        kind: EventKind,
        version: int,
        limit: int,
    ) -> list[OutboxJob[dict[str, Any]]]:
        rows = await self.conn.fetch(
            """
            SELECT *
            FROM outbox
            WHERE topic = $1
                AND kind = $2
                AND version = $3
                AND status = $4
                AND available_at <= $5
            ORDER BY available_at, id
            LIMIT $6
            """,
            topic.value,
            kind.value,
            version,
            JobStatus.PENDING.value,
            now(),
            limit,
        )
        if rows:
            logger.debug(
                "Read %s due outbox job(s) topic=%s kind=%s version=%s",
                len(rows),
                topic.value,
                kind.value,
                version,
            )
        return [OutboxJob.model_validate(dict(row)) for row in rows]

    async def claim(
        self,
        topic: EventTopic,
        kind: EventKind,
        version: int,
        limit: int,
    ) -> list[OutboxJob[dict[str, Any]]]:
        locked_at = now()
        cutoff = locked_at - timedelta(seconds=self.settings.claim_timeout_seconds)
        rows = await self.conn.fetch(
            """
            WITH due AS (
                SELECT id
                FROM outbox
                WHERE topic = $1
                    AND kind = $2
                    AND version = $3
                    AND available_at <= $4
                    AND (
                        status = $5
                        OR (status = $6 AND locked_at <= $7)
                    )
                ORDER BY available_at, id
                LIMIT $8
                FOR UPDATE SKIP LOCKED
            )

            UPDATE outbox
            SET status = $6,
                locked_at = $9,
                attempts = attempts + 1,
                updated_at = $9
            FROM due
            WHERE outbox.id = due.id
            RETURNING *
            """,
            topic.value,
            kind.value,
            version,
            locked_at,
            JobStatus.PENDING.value,
            JobStatus.RUNNING.value,
            cutoff,
            limit,
            locked_at,
        )

        jobs = [OutboxJob.model_validate(dict(row)) for row in rows]
        for job in jobs:
            await self.notify(job)

        if jobs:
            logger.info(
                "Claimed %s outbox row(s) topic=%s kind=%s version=%s",
                len(jobs),
                topic.value,
                kind.value,
                version,
            )
        return jobs

    async def mark(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        retry: bool = True,
    ) -> None:
        job = await self.get(job_id)
        if job is None:
            logger.warning(
                "Cannot mark missing outbox job id=%s status=%s", job_id, status
            )
            return

        status = JobStatus(status)
        timestamp = now()
        if status == JobStatus.DONE:
            row = await self.conn.fetchrow(
                """
                UPDATE outbox
                SET status = $2,
                    done_at = $3,
                    locked_at = NULL,
                    last_error = $4,
                    updated_at = $3
                WHERE id = $1
                RETURNING *
                """,
                job_id,
                JobStatus.DONE.value,
                timestamp,
                error,
            )
            assert row is not None, "Failed to mark outbox job done"
            marked = OutboxJob.model_validate(dict(row))
            logger.info("Marked outbox job done id=%s", job_id)
            await self.notify(marked)
            return

        if status == JobStatus.FAILED or not retry or job.attempts >= job.max_attempts:
            row = await self.conn.fetchrow(
                """
                UPDATE outbox
                SET status = $2,
                    locked_at = NULL,
                    last_error = $3,
                    updated_at = $4
                WHERE id = $1
                RETURNING *
                """,
                job_id,
                JobStatus.FAILED.value,
                error,
                timestamp,
            )
            assert row is not None, "Failed to mark outbox job failed"
            marked = OutboxJob.model_validate(dict(row))
            logger.error(
                "Marked outbox job failed id=%s attempts=%s max_attempts=%s error=%s",
                job_id,
                job.attempts,
                job.max_attempts,
                error,
            )
            await self.notify(marked)
            return

        row = await self.conn.fetchrow(
            """
            UPDATE outbox
            SET status = $2,
                available_at = $3,
                locked_at = NULL,
                last_error = $4,
                updated_at = $3
            WHERE id = $1
            RETURNING *
            """,
            job_id,
            JobStatus.PENDING.value,
            timestamp,
            error,
        )
        assert row is not None, "Failed to requeue outbox job"
        marked = OutboxJob.model_validate(dict(row))
        logger.warning(
            "Requeued outbox job id=%s attempts=%s max_attempts=%s error=%s",
            job_id,
            job.attempts,
            job.max_attempts,
            error,
        )
        await self.notify(marked)
