"""
scripts/run_migrations.py — Standalone migration runner.

Usage:
    python scripts/run_migrations.py

Connects directly to Postgres using settings.database_url, reads every .sql
file from migrations/ in alphabetical (filename) order, and executes them.

All SQL files use IF NOT EXISTS / ON CONFLICT DO NOTHING, so this script
is fully idempotent — safe to run on every deploy or manually at any time.

No Alembic — that's overkill for this project size.
"""

import asyncio
import os
import sys

# Ensure the project root is on the path when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations",
)


async def run() -> None:
    logger.info("Migration runner starting.")
    # Credentials are in the DSN — do not log it.
    logger.info("Connecting to Postgres… (DSN omitted from logs)")

    conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    try:
        sql_files = sorted(
            f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
        )

        if not sql_files:
            logger.warning("No .sql files found in %s — nothing to run.", MIGRATIONS_DIR)
            return

        for filename in sql_files:
            filepath = os.path.join(MIGRATIONS_DIR, filename)
            logger.info("Running migration: %s", filename)
            with open(filepath, "r", encoding="utf-8") as fh:
                sql = fh.read()
            await conn.execute(sql)
            logger.info("  ✓ %s completed.", filename)

        logger.info("All migrations applied successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
