"""psycopg3 connection pool with pgvector type registration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def _configure(conn: Connection) -> None:
    # The vector type only exists after migration 001 runs. Be defensive so the
    # pool can still hand out connections before the extension is installed
    # (e.g. a health check during first boot); the app creates a fresh pool after
    # migrations, at which point registration succeeds.
    try:
        register_vector(conn)
    except Exception:
        pass


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            configure=_configure,
            open=True,
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[Connection]:
    """Borrow a connection from the pool; commits on success, rolls back on error."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
