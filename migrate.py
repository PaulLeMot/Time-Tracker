"""Применяет миграции и подключает к Alembic базы старых установок."""

import asyncio
import os
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


BASELINE_REVISION = "20260930_0001"
PROJECT_DIR = Path(__file__).resolve().parent
LEGACY_MIGRATIONS_DIR = PROJECT_DIR / "migrations"
APPLICATION_TABLES = {
    "employees",
    "time_entries",
    "notifications",
    "tasks",
    "deals",
}


async def get_table_names() -> set[str]:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://timetracker:secret@db:5432/timetracker",
    )
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return set(
                await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_table_names()
                )
            )
    finally:
        await engine.dispose()


async def run_legacy_migrations() -> None:
    """Однократно доводит базы старых установок до состояния baseline."""
    database_url = make_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://timetracker:secret@db:5432/timetracker",
        )
    )
    connection = await asyncpg.connect(
        host=database_url.host,
        port=database_url.port or 5432,
        user=database_url.username,
        password=database_url.password,
        database=database_url.database,
    )
    try:
        for migration_path in sorted(LEGACY_MIGRATIONS_DIR.glob("*.sql")):
            print(f"Applying legacy migration: {migration_path.name}")
            await connection.execute(migration_path.read_text(encoding="utf-8"))
    finally:
        await connection.close()


def main() -> None:
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_DIR / "alembic"))
    table_names = asyncio.run(get_table_names())

    if "alembic_version" not in table_names and table_names & APPLICATION_TABLES:
        asyncio.run(run_legacy_migrations())
        print("Existing TimeTracker database detected; registering Alembic baseline.")
        command.stamp(config, BASELINE_REVISION)

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
