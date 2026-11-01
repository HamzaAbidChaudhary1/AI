"""PII redaction (Sentry before_send + logs), audit log, rate limiting."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request
from psycopg import Connection
from rahbar_agent.db import Jsonb

_PII_RES = [
    (re.compile(r"\b\d{5}-\d{7}-\d\b"), "[CNIC]"),            # Pakistani CNIC
    (re.compile(r"\b\d{13}\b"), "[CNIC]"),
    (re.compile(r"\b[A-Z]{2}\d{7}\b"), "[PASSPORT]"),          # PK passport format
    (re.compile(r"\bPK\d{2}[A-Z]{4}\d{16}\b"), "[IBAN]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\+?92[\s-]?3\d{2}[\s-]?\d{7}\b|\b03\d{2}[\s-]?\d{7}\b"), "[PHONE]"),
]
SENSITIVE_KEYS = {"passport_number", "cnic", "passport_number_enc", "cnic_enc", "content", "message", "input_text",
                  "authorization", "cookie", "data", "file", "extracted", "content_markdown"}


def redact_text(s: str) -> str:
    for rx, rep in _PII_RES:
        s = rx.sub(rep, s)
    return s


def redact(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[…]"
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in SENSITIVE_KEYS else redact(v, depth + 1)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, depth + 1) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def sentry_before_send(event: dict[str, Any], _hint: Any) -> dict[str, Any]:
    req = event.get("request") or {}
    req.pop("data", None)
    req.pop("cookies", None)
    if "headers" in req:
        req["headers"] = {k: v for k, v in req["headers"].items() if k.lower() not in ("authorization", "cookie")}
    event["request"] = req
    return redact(event)


def audit(conn: Connection, actor_id: str | None, role: str | None, action: str, entity: str,
          entity_id: str | None = None, data: dict[str, Any] | None = None) -> None:
    conn.execute("insert into audit_log (actor_id, actor_role, action, entity, entity_id, data) values (%s,%s,%s,%s,%s,%s)",
                 (actor_id, role, action, entity, entity_id, Jsonb(redact(data or {}))))


class RateLimiter:
    """Sliding window per key (in-process; put a shared store in front for multi-instance deploys)."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "too many requests, please wait a few minutes")
        q.append(now)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
