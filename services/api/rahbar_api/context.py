from __future__ import annotations

import contextvars

CURRENT_CASE: contextvars.ContextVar[str | None] = contextvars.ContextVar("case", default=None)
CURRENT_SESSION: contextvars.ContextVar[str | None] = contextvars.ContextVar("session", default=None)
