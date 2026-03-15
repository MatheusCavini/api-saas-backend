"""
Thread-safe Redis connector singleton. Initializes the connection pool once
using REDIS_URL (fallback: redis://localhost:6379/0). Provides get_client().
"""
import os
import threading
from typing import Optional

import redis
from redis import Redis

_lock = threading.Lock()
_pool: Optional[redis.ConnectionPool] = None
_default_url = "redis://localhost:6379/0"


def get_client() -> Redis:
    """Return the active Redis client instance from the shared pool. Thread-safe."""
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                url = os.environ.get("REDIS_URL", _default_url)
                _pool = redis.ConnectionPool.from_url(url)
    return Redis(connection_pool=_pool)


class ConnectorSingleton:
    """Thread-safe Redis connector. Use get_client() to obtain the Redis client."""

    _instance: Optional["ConnectorSingleton"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConnectorSingleton":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_pool") or self._pool is None:
            url = os.environ.get("REDIS_URL", _default_url)
            self._pool = redis.ConnectionPool.from_url(url)

    def get_client(self) -> Redis:
        """Return the active Redis client instance."""
        return Redis(connection_pool=self._pool)
