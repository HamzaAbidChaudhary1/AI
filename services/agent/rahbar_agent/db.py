"""Postgres access for the API/worker/agent (server-side, service-role connection)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def set_pool(p: ConnectionPool | None) -> None:
    global _pool
    _pool = p


@contextmanager
def tx() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """A transaction; commits on success, rolls back on error."""
    with pool().connection() as conn:
        with conn.transaction():
            yield conn


def fetch_all(sql: str, params: Any = None) -> list[dict[str, Any]]:
    with tx() as c:
        return list(c.execute(sql, params).fetchall())


def fetch_one(sql: str, params: Any = None) -> dict[str, Any] | None:
    with tx() as c:
        return c.execute(sql, params).fetchone()


def execute(sql: str, params: Any = None) -> None:
    with tx() as c:
        c.execute(sql, params)


__all__ = ["Jsonb", "execute", "fetch_all", "fetch_one", "pool", "set_pool", "tx"]
