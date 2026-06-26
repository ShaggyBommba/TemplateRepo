from __future__ import annotations

import asyncio
from collections.abc import Iterator
from logging import getLogger
from os import environ
from pathlib import Path
import subprocess

from asyncpg import utils
import asyncpg
import dotenv
import pytest

from infrastructure.config import Settings, get_settings

logger = getLogger(__name__)

ROOT = Path.cwd()
ENV_FILE = ".env"
TEST_DB = "test"


def env(path: Path) -> None:
    """Load environment variables from the .env file if it exists."""
    if path.exists():
        logger.info(f"Loading environment variables from {path}")
        dotenv.load_dotenv(dotenv_path=path)
    else:
        logger.warning(
            f"Environment file {path} does not exist. Using system environment variables."
        )


def run(
    command: list[str], cwd: Path = Path.cwd(), env: dict[str, str] | None = None
) -> None:
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


@pytest.fixture(scope="session", autouse=True)
def infrastructure() -> Iterator[None]:
    """Set up the test infrastructure before running tests."""
    path = ROOT / ENV_FILE
    env(path)

    logger.info("Starting test infrastructure...")
    run(
        [
            "docker",
            "compose",
            "-f",
            "infrastructure/docker-compose.yml",
            "--profile",
            "infrastructure",
            "up",
            "-d",
        ]
    )

    yield

    logger.info("Stopping test infrastructure...")
    run(
        [
            "docker",
            "compose",
            "-f",
            "infrastructure/docker-compose.yml",
            "--profile",
            "infrastructure",
            "down",
            "--volumes",
            "--remove-orphans",
        ]
    )


@pytest.fixture(scope="session", autouse=True)
def database(infrastructure: None) -> Iterator[None]:
    """Create a disposable test database for the test session."""
    path = ROOT / ENV_FILE
    settings = get_settings(env_file=path)

    logger.info(f"Creating test database: {TEST_DB}")
    asyncio.run(create_database(settings, TEST_DB))

    sandbox = environ.copy()
    sandbox["APP_DATABASE__DATABASE"] = TEST_DB

    logger.info(f"Running migrations on test database: {TEST_DB}")
    run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "infrastructure.persistence.migrations",
            "upgrade",
        ],
        env=sandbox,
    )

    yield

    logger.info(f"Dropping test database: {TEST_DB}")
    asyncio.run(drop_database(settings, TEST_DB))


@pytest.fixture(scope="session")
def settings(database) -> Settings:
    """Return settings configured for the test database."""
    path = ROOT / ENV_FILE
    logger.info(f"Loading environment variables from {path}")
    dotenv.load_dotenv(dotenv_path=path)
    settings = get_settings(env_file=path)
    database = settings.database.model_copy(update={"database": TEST_DB})
    return settings.model_copy(update={"database": database})


async def create_database(settings: Settings, name: str) -> None:
    conn = await asyncpg.connect(settings.database.asyncpg_dsn)
    try:
        await conn.fetchval("SELECT format('CREATE DATABASE %I', $1::text)", name)
    except asyncpg.DuplicateDatabaseError:
        logger.info("Test database already exists, continuing")
    finally:
        await conn.close()


async def drop_database(settings: Settings, name: str) -> None:
    conn = await asyncpg.connect(settings.database.asyncpg_dsn)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1",
            name,
        )
        await conn.fetchval("SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE)', $1::text)", name)
    finally:
        await conn.close()