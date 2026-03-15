"""
Database connection module. Reads DATABASE_URL from environment and exposes
get_connection() / get_cursor() for use by controllers. Can be mocked in tests.
"""
import os
import psycopg2
from contextlib import contextmanager
from typing import Generator, Any

_connection_params: dict[str, Any] | None = None


def _get_params() -> dict[str, Any]:
    global _connection_params
    if _connection_params is None:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL environment variable is not set")
        _connection_params = {"dsn": url}
    return _connection_params


@contextmanager
def get_connection():
    """Yield a database connection. Caller must close or use as context manager."""
    params = _get_params()
    conn = psycopg2.connect(**params)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor():
    """Yield a cursor from a new connection. Connection is closed when cursor context exits."""
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
