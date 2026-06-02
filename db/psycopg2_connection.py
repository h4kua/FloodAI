"""
Raw psycopg2 connection helpers for the flood_ai PostgreSQL database.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Iterator, Optional

from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.pool import ThreadedConnectionPool

if os.getenv("FLOOD_LOAD_DOTENV", "1") == "1":
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

DB_HOST = os.getenv("DB_HOST")

def _required_password() -> str:
    password = os.getenv("DB_PASSWORD")
    if password is None or not password.strip():
        raise RuntimeError("DB_PASSWORD must be set")
    return password


def _validated_password(password: Optional[str]) -> str:
    if isinstance(password, str) and password.strip():
        return password.strip()
    return _required_password()


@dataclass(frozen=True)
class Psycopg2ConnectionConfig:
    """Connection settings loaded from environment variables."""

    host: str = ""
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""
    connect_timeout: int = 10
    application_name: str = ""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        connect_timeout: Optional[int] = None,
        application_name: Optional[str] = None,
    ) -> None:
        object.__setattr__(self, "host", host or os.getenv("DB_HOST", "localhost"))
        object.__setattr__(
            self,
            "port",
            int(port if port is not None else os.getenv("DB_PORT", "5432")),
        )
        object.__setattr__(self, "database", database or os.getenv("DB_NAME", "flood_ai"))
        object.__setattr__(self, "user", user or os.getenv("DB_USER", "postgres"))
        object.__setattr__(self, "password", _validated_password(password))
        object.__setattr__(
            self,
            "connect_timeout",
            int(
                connect_timeout
                if connect_timeout is not None
                else os.getenv("DB_CONNECT_TIMEOUT", "10")
            ),
        )
        object.__setattr__(
            self,
            "application_name",
            application_name or os.getenv("DB_APP_NAME", "flood-ai-pipeline"),
        )


_POOL: ThreadedConnectionPool | None = None
_POOL_LOCK = Lock()


def _init_pool(config: Psycopg2ConnectionConfig) -> ThreadedConnectionPool:
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = ThreadedConnectionPool(
                    minconn=int(os.getenv("DB_POOL_MIN", "2")),
                    maxconn=int(os.getenv("DB_POOL_MAX", "20")),
                    dsn=f"postgresql://{config.user}:{config.password}@{config.host}:{config.port}/{config.database}?sslmode=require&connect_timeout={config.connect_timeout}&application_name={config.application_name}"
                )
    return _POOL


@contextmanager
def pooled_connection(
    config: Optional[Psycopg2ConnectionConfig] = None,
) -> Iterator[PgConnection]:
    """
    Borrow a PostgreSQL connection from the process-wide thread-safe pool.

    Callers own commit/rollback inside the context. The connection is always
    returned to the pool instead of being closed.
    """
    active_config = config or Psycopg2ConnectionConfig()
    pool = _init_pool(active_config)
    connection = pool.getconn()
    try:
        connection.autocommit = False
        yield connection
    finally:
        pool.putconn(connection)


def close_pool() -> None:
    global _POOL
    if _POOL is not None:
        with _POOL_LOCK:
            if _POOL is not None:
                _POOL.closeall()
                _POOL = None


def get_psycopg2_connection(
    config: Optional[Psycopg2ConnectionConfig] = None,
) -> PgConnection:
    """
    Create a psycopg2 connection with autocommit disabled.

    The caller owns commit/rollback/close so one transaction can span the
    entire multi-stage pipeline write.
    """
    active_config = config or Psycopg2ConnectionConfig()
    dsn = (
        f"postgresql://{active_config.user}:{active_config.password}"
        f"@{active_config.host}:{active_config.port}/{active_config.database}"
        f"?sslmode=require&connect_timeout={active_config.connect_timeout}"
        f"&application_name={active_config.application_name}"
    )
    connection = psycopg2.connect(dsn)
    connection.autocommit = False
    return connection
