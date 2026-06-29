"""Idempotent migration runner.

Applies ``migrations/*.sql`` in filename order, recording each applied file in a
``schema_version`` table so re-runs are no-ops. Designed to run against the
docker-compose ``db`` service (no host psql required) and the CI pgvector service.

Usage:
    python -m app.db.migrate
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import Connection

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _applied(conn: Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_version")
        return {row[0] for row in cur.fetchall()}


def apply_migrations(conn: Connection) -> list[str]:
    """Apply pending migrations in order. Returns the filenames applied this run."""
    conn.execute(_SCHEMA_VERSION_DDL)
    conn.commit()

    done = _applied(conn)
    applied: list[str] = []
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.name in done:
            continue
        sql = sql_file.read_text(encoding="utf-8")
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_version (filename) VALUES (%s)",
                (sql_file.name,),
            )
        applied.append(sql_file.name)
    return applied


def main() -> None:
    # Use a plain connection (not the pgvector-registered pool): migrations create
    # the vector extension, so the type may not exist yet at this point.
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        applied = apply_migrations(conn)
    if applied:
        print("Applied migrations:", ", ".join(applied))
    else:
        print("No pending migrations; schema is up to date.")


if __name__ == "__main__":
    main()
