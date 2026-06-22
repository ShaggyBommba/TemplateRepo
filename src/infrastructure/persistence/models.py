from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from domain.entity import (
    OutboxJob,
)
from domain.value import EventKind, EventTopic, JobStatus
from infrastructure.persistence.database import Base
from utils.time import now


class OutboxRow(Base):
    """Durable queued work row."""

    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(256),
        unique=True,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=JobStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now,
        onupdate=now,
        nullable=False,
    )

    def to_domain(self) -> OutboxJob[dict[str, Any]]:
        """Convert this row into an outbox job."""
        return OutboxJob(
            id=self.id,
            trace_id=self.trace_id,
            idempotency_key=self.idempotency_key,
            topic=EventTopic(self.topic),
            kind=EventKind(self.kind),
            version=self.version,
            payload=self.payload,
            status=JobStatus(self.status),
            attempts=self.attempts,
            max_attempts=self.max_attempts,
            available_at=self.available_at,
            locked_at=self.locked_at,
            done_at=self.done_at,
            last_error=self.last_error,
        )
