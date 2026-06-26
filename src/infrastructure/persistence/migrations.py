from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from infrastructure.config import get_settings

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_DIR = ROOT / "migrations" / "versions"
VERSION_TABLE = "schema_migrations"
LEGACY_VERSION_TABLE = "alembic_version"


@dataclass(frozen=True)
class Migration:
    revision: str
    down_revision: str | None
    path: Path
    sql: str


def migrations(path: Path = MIGRATION_DIR) -> list[Migration]:
    """Load SQL migrations from disk in dependency order."""
    loaded = [load(file) for file in sorted(path.glob("*.sql"))]
    by_revision = {migration.revision: migration for migration in loaded}
    if len(by_revision) != len(loaded):
        raise RuntimeError("Duplicate migration revision detected")

    ordered: list[Migration] = []
    seen: set[str] = set()
    remaining = set(by_revision)
    while remaining:
        progressed = False
        for revision in sorted(remaining):
            migration = by_revision[revision]
            parent = migration.down_revision
            if parent is None or parent in seen:
                ordered.append(migration)
                seen.add(revision)
                remaining.remove(revision)
                progressed = True
                break
        if not progressed:
            blocked = ", ".join(sorted(remaining))
            raise RuntimeError(f"Migration chain is incomplete or cyclic: {blocked}")
    return ordered


def load(path: Path) -> Migration:
    """Load one SQL migration file."""
    sql = path.read_text(encoding="utf-8")
    revision = metadata(sql, "revision") or path.stem.split("_", 1)[0]
    down_revision = metadata(sql, "down_revision") or None
    return Migration(
        revision=revision,
        down_revision=down_revision,
        path=path,
        sql=sql,
    )


def metadata(sql: str, key: str) -> str | None:
    for line in sql.splitlines():
        match = re.fullmatch(rf"\s*--\s*{key}\s*:\s*(.*?)\s*", line)
        if match is not None:
            value = match.group(1).strip()
            return value or None
        if line.strip() and not line.lstrip().startswith("--"):
            return None
    return None


async def upgrade(target: str = "head") -> None:
    """Apply pending migrations through asyncpg."""
    ordered = migrations()
    if target != "head" and target not in {migration.revision for migration in ordered}:
        raise RuntimeError(f"Unknown migration target: {target}")

    settings = get_settings()
    conn = await asyncpg.connect(settings.database.asyncpg_dsn)
    try:
        async with conn.transaction():
            await ensure_table(conn)
            await seed_legacy_alembic_revision(conn, ordered)
            applied = await applied_revisions(conn)
            for migration in ordered:
                if migration.revision in applied:
                    if migration.revision == target:
                        break
                    continue
                await conn.execute(migration.sql)
                await conn.execute(
                    f"INSERT INTO {VERSION_TABLE} (revision) VALUES ($1)",
                    migration.revision,
                )
                if migration.revision == target:
                    break
    finally:
        await conn.close()


async def ensure_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
            revision VARCHAR(128) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def seed_legacy_alembic_revision(
    conn: asyncpg.Connection,
    ordered: list[Migration],
) -> None:
    legacy_table = await conn.fetchval("SELECT to_regclass($1)", LEGACY_VERSION_TABLE)
    if legacy_table is None:
        return
    legacy = await conn.fetchval(f"SELECT version_num FROM {LEGACY_VERSION_TABLE}")
    if legacy is None:
        return
    revisions = [migration.revision for migration in ordered]
    if legacy not in revisions:
        return
    for revision in revisions[: revisions.index(legacy) + 1]:
        await conn.execute(
            f"""
            INSERT INTO {VERSION_TABLE} (revision)
            VALUES ($1)
            ON CONFLICT (revision) DO NOTHING
            """,
            revision,
        )


async def applied_revisions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(f"SELECT revision FROM {VERSION_TABLE}")
    return {row["revision"] for row in rows}


def revision(message: str) -> Path:
    """Create a new manual SQL migration file."""
    MIGRATION_DIR.mkdir(parents=True, exist_ok=True)
    existing = migrations()
    parent = existing[-1].revision if existing else None
    now = datetime.now(UTC)
    migration_id = now.strftime("%Y%m%d%H%M%S")
    slug = slugify(message)
    path = MIGRATION_DIR / f"{migration_id}_{slug}.sql"
    path.write_text(template(message, migration_id, parent, now), encoding="utf-8")
    return path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "migration"


def template(message: str, migration_id: str, parent: str | None, now: datetime) -> str:
    return f"""-- {message}.
-- revision: {migration_id}
-- down_revision: {parent or ""}
-- create_date: {now.isoformat()}

"""


def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage asyncpg database migrations.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    upgrade_cmd = subcommands.add_parser("upgrade", help="Apply migrations.")
    upgrade_cmd.add_argument("target", nargs="?", default="head")

    revision_cmd = subcommands.add_parser("revision", help="Create a migration file.")
    revision_cmd.add_argument("message")

    return parser.parse_args()


def main() -> None:
    args = parse()
    if args.command == "upgrade":
        asyncio.run(upgrade(args.target))
        return
    if args.command == "revision":
        path = revision(args.message)
        print(path.relative_to(ROOT))
        return
    raise RuntimeError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
