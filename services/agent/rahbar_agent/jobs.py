"""Postgres-backed job queue (jobs table, SELECT ... FOR UPDATE SKIP LOCKED)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from .db import Jsonb, tx


def enqueue(type_: str, payload: dict[str, Any] | None = None, *, run_at: datetime | None = None,
            conn: Connection | None = None, max_attempts: int = 3) -> str:
    sql = """insert into jobs (type, payload, run_at, max_attempts)
             values (%s, %s, coalesce(%s, now()), %s) returning id"""
    params = (type_, Jsonb(payload or {}), run_at, max_attempts)
    if conn is not None:
        return str(conn.execute(sql, params).fetchone()["id"])
    with tx() as c:
        return str(c.execute(sql, params).fetchone()["id"])


def claim_next(conn: Connection, types: list[str] | None = None) -> dict[str, Any] | None:
    row = conn.execute(
        """update jobs set status='running', attempts=attempts+1, locked_at=now()
           where id = (
             select id from jobs
             where status='queued' and run_at <= now() and (%(types)s::text[] is null or type = any(%(types)s))
             order by run_at
             for update skip locked
             limit 1)
           returning *""",
        {"types": types},
    ).fetchone()
    return row


def finish(conn: Connection, job_id: str, result: dict[str, Any] | None = None) -> None:
    conn.execute("update jobs set status='done', result=%s, last_error=null where id=%s", (Jsonb(result or {}), job_id))


def fail(conn: Connection, job: dict[str, Any], error: str) -> None:
    # exponential backoff; give up after max_attempts. Never store PII in errors.
    retry = job["attempts"] < job["max_attempts"]
    conn.execute(
        """update jobs set status=%s, last_error=%s,
                  run_at = now() + make_interval(secs => 30 * power(2, attempts))
           where id=%s""",
        ("queued" if retry else "failed", error[:500], job["id"]),
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    with tx() as c:
        return c.execute("select id, type, status, attempts, result, last_error, created_at, updated_at from jobs where id=%s",
                         (job_id,)).fetchone()
