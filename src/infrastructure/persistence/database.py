from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from infrastructure.config import DatabaseSettings


class AsyncpgDatabase:
    """asyncpg database factory for pools and direct connections."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.pool_cache: asyncpg.Pool | None = None

    async def pool(self) -> asyncpg.Pool:
        """Return the shared asyncpg pool, creating it lazily."""
        if self.pool_cache is None:
            self.pool_cache = await asyncpg.create_pool(
                dsn=self.settings.asyncpg_dsn,
                init=self.setup,
            )
        return self.pool_cache

    async def setup(self, conn: asyncpg.Connection) -> None:
        """Configure JSON codecs for domain-shaped payloads."""
        for name in ("json", "jsonb"):
            await conn.set_type_codec(
                name,
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
                format="text",
            )

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[PoolConnectionProxy, None]:
        """Yield one pooled connection for direct adapter use."""
        pool = await self.pool()
        async with pool.acquire() as conn:
            yield conn

    async def close(self) -> None:
        """Close the shared asyncpg pool."""
        if self.pool_cache is not None:
            await self.pool_cache.close()
            self.pool_cache = None
