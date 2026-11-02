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
_resolved_url: str | None = None


def database_url() -> str:
    """DATABASE_URL may hold several candidates separated by '|' (e.g. the two Supabase pooler hosts);
    the first one that accepts a connection is used for the life of the process."""
    global _resolved_url
    if _resolved_url is None:
        candidates = [c.strip() for c in get_settings().database_url.split("|") if c.strip()]
        if len(candidates) == 1:
            _resolved_url = candidates[0]
        else:
            last: Exception | None = None
            for c in candidates:
                try:
                    with psycopg.connect(c, connect_timeout=8):
                        _resolved_url = c
                        break
                except psycopg.OperationalError as e:
                    last = e
            if _resolved_url is None:
                raise RuntimeError("no DATABASE_URL candidate accepted a connection") from last
    return _resolved_url


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            database_url(),
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
