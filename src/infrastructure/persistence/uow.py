from __future__ import annotations

import logging
from typing import Self, Any

from asyncpg.pool import PoolConnectionProxy
from asyncpg.transaction import Transaction

from application.adapters.core import UnitOfWork
from infrastructure.config import OutboxSettings
from infrastructure.persistence.database import AsyncpgDatabase
from infrastructure.persistence.repository.outbox import OutboxRepo


logger = logging.getLogger(__name__)


class AsyncpgUnitOfWork(UnitOfWork):
    """asyncpg-backed unit of work for repository transactions."""

    def __init__(
        self,
        database: AsyncpgDatabase,
        outbox_settings: OutboxSettings,
    ) -> None:
        self.database = database
        self.outbox_settings = outbox_settings

        self.active: PoolConnectionProxy | None = None
        self.transaction: Transaction | None = None
        self.committed = False

    @property
    def connection(self) -> PoolConnectionProxy:
        if self.active is None:
            raise RuntimeError("AsyncpgUnitOfWork must be entered before use.")
        return self.active

    async def __aenter__(self) -> Self:
        pool = await self.database.pool()
        conn = await pool.acquire()
        self.active = conn
        transaction = conn.transaction()
        await transaction.start()
        self.transaction = transaction
        self.committed = False
        logger.debug("Opened asyncpg unit of work")

        self.outbox = OutboxRepo(
            self.connection,
            self.outbox_settings,
        )
        self.job = self.outbox

        return self

    async def __aexit__(
        self,
        error: type[BaseException] | None,
        *args: Any,
    ) -> None:
        try:
            # 1. Trigger rollback if an exception happened OR if we just forgot to commit
            if error is not None:
                logger.debug(
                    "Rolling back asyncpg unit of work due to exception: %s",
                    error.__name__,
                )
                await self.rollback()
            elif not self.committed:
                logger.debug("Rolling back uncommitted asyncpg unit of work")
                await self.rollback()
                
        finally:
            # 2. Guarantee cleanup and connection release
            if self.active is not None:
                try:
                    pool = await self.database.pool()
                    await pool.release(self.active)
                except Exception:
                    logger.exception("Failed to release asyncpg connection to pool")
                finally:
                    self.active = None
                    
            self.transaction = None
            logger.debug("Closed asyncpg unit of work")

    async def commit(self) -> None:
        if self.transaction is None:
            raise RuntimeError("AsyncpgUnitOfWork must be entered before commit.")
        await self.transaction.commit()
        self.transaction = None
        self.committed = True
        logger.debug("Committed asyncpg unit of work")

    async def rollback(self) -> None:
        if self.transaction is None:
            return
        await self.transaction.rollback()
        self.transaction = None
        logger.debug("Rolled back asyncpg unit of work")
