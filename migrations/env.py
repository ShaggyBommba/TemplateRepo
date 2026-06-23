from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from infrastructure.config import get_settings
from infrastructure.persistence.database import Base

import infrastructure.persistence.models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def url() -> str:
    """Return the database URL from application settings."""
    return get_settings().database.dsn


def include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Ignore database objects that are not owned by application metadata."""
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations without opening a DBAPI connection."""
    context.configure(
        url=url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
