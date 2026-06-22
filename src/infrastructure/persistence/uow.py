from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from application.adapters.core import UnitOfWork
from infrastructure.config import OutboxSettings
from infrastructure.persistence.repository.outbox import OutboxRepo


logger = logging.getLogger(__name__)


class SqlUnitOfWork(UnitOfWork):
    """SQLAlchemy-backed unit of work for repository transactions."""

    job: OutboxRepo
    outbox: OutboxRepo

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        outbox_settings: OutboxSettings,
    ) -> None:
        self.session_factory = session_factory
        self.outbox_settings = outbox_settings

        self.active: Session | None = None
        self.committed = False

    @property
    def session(self) -> Session:
        if self.active is None:
            raise RuntimeError("SqlUnitOfWork must be entered before use.")
        return self.active

    def __enter__(self) -> Self:
        self.active = self.session_factory()
        self.committed = False
        logger.debug("Opened SQL unit of work")

        self.outbox = OutboxRepo(
            self.session,
            self.outbox_settings,
        )
        self.job = self.outbox

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self.committed:
                if exc_type is not None:
                    logger.debug(
                        "Rolling back SQL unit of work because exception occurred exc_type=%s",
                        exc_type.__name__,
                    )
                else:
                    logger.debug("Rolling back uncommitted SQL unit of work")
                self.rollback()
        finally:
            self.session.close()
            self.active = None
            logger.debug("Closed SQL unit of work")

    def commit(self) -> None:
        self.session.commit()
        self.committed = True
        logger.debug("Committed SQL unit of work")

    def rollback(self) -> None:
        self.session.rollback()
        logger.debug("Rolled back SQL unit of work")
