"""POST /chat — SSE stream of agent events (docs/AGENT.md "Streaming protocol")."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import uuid
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field
from rahbar_agent.db import database_url, fetch_one, tx
from rahbar_agent.graph.graph import build_graph, thread_config, turn_input

from .auth import User, optional_user
from .context import CURRENT_CASE, CURRENT_SESSION
from .security import RateLimiter

log = logging.getLogger(__name__)
router = APIRouter()
_graph: Any = None
_chat_limiter = RateLimiter(limit=40, window_s=600)


def get_graph() -> Any:
    global _graph
    if _graph is None:
        if os.environ.get("CHECKPOINTER", "postgres") == "memory":
            from langgraph.checkpoint.memory import InMemorySaver
            saver: Any = InMemorySaver()
        else:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(database_url(), max_size=10, open=True,
                                  kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
            saver = PostgresSaver(pool)  # type: ignore[arg-type]
            saver.setup()
            lock_down_checkpoint_tables(pool)
        _graph = build_graph(saver)
    return _graph


CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")


def lock_down_checkpoint_tables(pool: Any) -> None:
    """LangGraph creates its tables in `public`; on Supabase those would be readable through the
    browser-facing REST API. Conversations are private: enable RLS (no policies) and revoke client roles."""
    with pool.connection() as conn:
        roles = {r["rolname"] for r in conn.execute(
            "select rolname from pg_roles where rolname in ('anon','authenticated')").fetchall()}
        for t in CHECKPOINT_TABLES:
            if conn.execute("select to_regclass(%s) as r", (f"public.{t}",)).fetchone()["r"] is None:
                continue
            conn.execute(f"alter table public.{t} enable row level security")  # noqa: S608
            if roles:
                conn.execute(f"revoke all on public.{t} from {', '.join(sorted(roles))}")  # noqa: S608


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=8000)
    locale: Literal["en", "ur"] = "en"
    session_id: str | None = Field(default=None, max_length=64)
    case_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    resume: dict[str, Any] | None = None


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def thread_id_for(user: User | None, body: ChatIn) -> str:
    """Thread ids are derived server-side so nobody can attach to another user's conversation."""
    if body.case_id:
        if user is None:
            raise HTTPException(401, "sign in required")
        row = fetch_one("select owner_id from cases where id=%s", (body.case_id,))
        if row is None or str(row["owner_id"]) != user.id:
            raise HTTPException(404, "case not found")
        return f"case:{body.case_id}"
    sid = body.session_id or uuid.uuid4().hex
    return f"user:{user.id}:{sid}" if user else f"anon:{sid}"


@router.post("/chat")
def chat(body: ChatIn, user: User | None = Depends(optional_user)) -> StreamingResponse:
    if not body.message.strip() and not body.payload and not body.resume:
        raise HTTPException(422, "empty message")
    _chat_limiter.check(user.id if user else (body.session_id or "anon"))
    thread = thread_id_for(user, body)
    cfg = thread_config(thread)
    graph = get_graph()
    if body.resume is not None:
        inp: Any = Command(resume=body.resume)
    else:
        inp = turn_input(body.message, locale=body.locale, user_id=user.id if user else None,
                         session_id=body.session_id, case_id=body.case_id, payload=body.payload)

    def run_turn(q: queue.Queue[str | None]) -> None:
        # one thread per turn so context (case/session for usage accounting) is stable for the whole run
        CURRENT_CASE.set(body.case_id)
        CURRENT_SESSION.set(thread)
        try:
            for chunk in graph.stream(inp, cfg, stream_mode="custom"):
                q.put(sse(chunk["event"], chunk["data"]))
            state = graph.get_state(cfg)
            for intr in state.interrupts:
                q.put(sse("card", intr.value.get("card", intr.value)))
            if state.values.get("case_id") and not body.case_id:
                q.put(sse("case", {"case_id": state.values["case_id"]}))
        except Exception:
            log.exception("chat turn failed")
            msg = ("Sorry — something went wrong on our side. Nothing was submitted or charged. Please try again."
                   if body.locale == "en" else "معذرت — ہماری طرف سے کوئی خرابی ہوئی۔ کچھ جمع یا چارج نہیں ہوا۔ دوبارہ کوشش کریں۔")
            q.put(sse("error", {"message": msg}))
        q.put(sse("done", {}))
        q.put(None)

    def gen() -> Iterator[str]:
        yield sse("session", {"thread": thread, "session_id": thread.split(":")[-1]})
        q: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=run_turn, args=(q,), daemon=True).start()
        while (item := q.get()) is not None:
            yield item

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/chat/history")
def history(session_id: str | None = None, case_id: str | None = None,
            user: User | None = Depends(optional_user)) -> dict[str, Any]:
    thread = thread_id_for(user, ChatIn(session_id=session_id, case_id=case_id, message="x"))
    st = get_graph().get_state(thread_config(thread))
    msgs = st.values.get("messages", []) if st and st.values else []
    return {"messages": msgs[-50:], "interrupts": [i.value for i in (st.interrupts if st else [])]}


def record_usage(usage: Any, node: str | None) -> None:
    try:
        with tx() as conn:
            conn.execute("insert into llm_usage (case_id, session_id, model, input_tokens, output_tokens, node) values (%s,%s,%s,%s,%s,%s)",
                         (CURRENT_CASE.get(), CURRENT_SESSION.get(), usage.model, usage.input_tokens, usage.output_tokens, node))
    except Exception:
        log.exception("usage insert failed")
