from __future__ import annotations

from collections.abc import Iterator
from logging import getLogger
from os import environ
from pathlib import Path
import subprocess

import dotenv
import pytest
from psycopg import connect, sql
from psycopg.errors import DuplicateDatabase

from infrastructure.config import Settings, get_settings

logger = getLogger(__name__)

ENV_FILE = ".env"
TEST_DB = "test"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        output = result.stdout.strip()
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}\n"
            f"{output}"
        )


def env_path() -> Path:
    path = Path.cwd() / ENV_FILE
    if not path.exists():
        raise RuntimeError(
            f"{ENV_FILE} is required and was not found. "
            "Copy .env and adjust test-specific DB settings."
            f"Expected path: {path.resolve()}"
        )
    return path


@pytest.fixture(scope="session", autouse=True)
def infrastructure() -> Iterator[None]:
    """Set up the test infrastructure before running tests."""
    root = Path.cwd()
    path = env_path()
    dotenv.load_dotenv(dotenv_path=path)

    logger.info("Starting test infrastructure...")
    run(["task", "infra:up"], cwd=root)

    yield

    logger.info("Stopping test infrastructure...")
    run(["task", "infra:down"], cwd=root)


@pytest.fixture(scope="session", autouse=True)
def database(infrastructure: None) -> Iterator[None]:
    root = Path.cwd()
    path = env_path()
    dotenv.load_dotenv(dotenv_path=path)
    settings = get_settings(env_file=path)

    logger.info(f"Creating test database: {TEST_DB}")
    with connect(settings.database.psycopg_dsn, autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB))
                )
            except DuplicateDatabase:
                logger.info("Test database already exists, continuing")

    sandbox = environ.copy()
    sandbox["APP_DATABASE__DATABASE"] = TEST_DB

    run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=root,
        env=sandbox,
    )

    yield

    logger.info(f"Dropping test database: {TEST_DB}")
    with connect(settings.database.psycopg_dsn, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = %s"
                ),
                (TEST_DB,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(TEST_DB))
            )


@pytest.fixture(scope="session")
def settings(database) -> Settings:
    """Return settings configured for the test database."""
    path = env_path()
    dotenv.load_dotenv(dotenv_path=path)
    settings = get_settings(env_file=path)
    database = settings.database.model_copy(update={"database": TEST_DB})
    return settings.model_copy(update={"database": database})
