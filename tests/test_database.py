from __future__ import annotations

from typing import Any

import psycopg
import pytest
from pydantic import SecretStr

from infrastructure.config import DatabaseSettings
from infrastructure.persistence.database import (
    Base,
    KEY,
    NAMESPACE,
    SqlDatabase,
)


class FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeConnection:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def execute(self, statement: Any, params: dict[str, int]) -> None:
        self.calls.append((str(statement), params))


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeConnection:
        return self.connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, dialect_name: str, calls: list[tuple[str, Any]]) -> None:
        self.dialect = FakeDialect(dialect_name)
        self.connection = FakeConnection(calls)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeAsyncConnection:
    async def __aenter__(self) -> "FakeAsyncConnection":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_create_all_serializes_postgresql_schema_creation(monkeypatch) -> None:
    calls: list[tuple[str, Any]] = []
    engine = FakeEngine("postgresql", calls)
    database = SqlDatabase(DatabaseSettings(provider="postgresql"))
    database.engine = lambda: engine  # type: ignore[method-assign]

    def create_all(bind: Any) -> None:
        calls.append(("create_all", bind))

    monkeypatch.setattr(Base.metadata, "create_all", create_all)

    database.create_all()

    assert calls[0] == (
        "SELECT pg_advisory_xact_lock(:ns, :key)",
        {"ns": NAMESPACE, "key": KEY},
    )
    assert calls[1] == ("create_all", engine.connection)


def test_create_all_uses_plain_metadata_creation_for_sqlite(monkeypatch) -> None:
    calls: list[tuple[str, Any]] = []
    engine = FakeEngine("sqlite", calls)
    database = SqlDatabase(DatabaseSettings(provider="sqlite"))
    database.engine = lambda: engine  # type: ignore[method-assign]

    def create_all(bind: Any) -> None:
        calls.append(("create_all", bind))

    monkeypatch.setattr(Base.metadata, "create_all", create_all)

    database.create_all()

    assert calls == [("create_all", engine)]


def test_postgresql_settings_expose_plain_psycopg_dsn() -> None:
    settings = DatabaseSettings(
        provider="postgresql",
        host="db",
        port=6543,
        user="user",
        password=SecretStr("secret"),
        database="service",
    )

    assert settings.dsn == "postgresql+psycopg://user:secret@db:6543/service"
    assert settings.psycopg_dsn == "postgresql://user:secret@db:6543/service"


def test_psycopg_dsn_requires_postgresql_provider() -> None:
    settings = DatabaseSettings(provider="sqlite")

    with pytest.raises(ValueError, match="postgresql provider"):
        settings.psycopg_dsn


async def test_connection_uses_plain_psycopg_dsn(monkeypatch) -> None:
    calls: list[str] = []

    async def connect(dsn: str) -> FakeAsyncConnection:
        calls.append(dsn)
        return FakeAsyncConnection()

    monkeypatch.setattr(psycopg.AsyncConnection, "connect", connect)
    settings = DatabaseSettings(
        provider="postgresql",
        host="db",
        port=6543,
        user="user",
        password=SecretStr("secret"),
        database="service",
    )
    database = SqlDatabase(settings)

    async with database.connection() as conn:
        assert isinstance(conn, FakeAsyncConnection)

    assert calls == ["postgresql://user:secret@db:6543/service"]
