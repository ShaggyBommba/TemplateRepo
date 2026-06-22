from __future__ import annotations

from typing import Any

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
