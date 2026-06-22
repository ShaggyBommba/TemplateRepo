from __future__ import annotations
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import psycopg
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from infrastructure.config import DatabaseSettings

NAMESPACE = int.from_bytes(b"tmpl", "big")
KEY = 1


class Base(DeclarativeBase):
    """Infrastructure foundation that our Shared Kernel models inherit from."""


class SqlDatabase:
    """SQLAlchemy database factory for engines, sessions, and schema setup."""

    def __init__(self, settings: DatabaseSettings) -> None:
        """Keep database settings and lazily create SQLAlchemy objects."""
        self.settings = settings
        self.engine_cache: Engine | None = None
        self.sessions_cache: sessionmaker[Session] | None = None

    def engine(self) -> Engine:
        """Return the shared engine, applying driver-specific options."""
        if self.engine_cache is None:
            engine = create_engine(self.settings.dsn)
            self.engine_cache = engine
        return self.engine_cache

    def sessions(self) -> sessionmaker[Session]:
        """Return the session factory used by repositories and units of work."""
        if self.sessions_cache is None:
            self.sessions_cache = sessionmaker(bind=self.engine())
        return self.sessions_cache

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[psycopg.AsyncConnection, None]:
        async with await psycopg.AsyncConnection.connect(self.settings.dsn) as conn:
            yield conn

    def create_all(self) -> None:
        """Provision extensions and create all known database tables."""
        import infrastructure.persistence.models  # noqa: F401

        engine = self.engine()
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(:ns, :key)"),
                    {"ns": NAMESPACE, "key": KEY},
                )
                Base.metadata.create_all(conn)
            return

        Base.metadata.create_all(engine)

    def drop_all(self) -> None:
        """Drop all known database tables."""
        import infrastructure.persistence.models  # noqa: F401

        Base.metadata.drop_all(self.engine())

    def close(self) -> None:
        """Dispose the engine and session factory."""
        if self.engine_cache is not None:
            self.engine_cache.dispose()
            self.engine_cache = None
            self.sessions_cache = None
