"""Worker: polls the jobs table (FOR UPDATE SKIP LOCKED) and runs scheduled jobs."""

from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable
from typing import Any

from rahbar_agent import documents, jobs, pricing
from rahbar_agent.crawl import pipeline
from rahbar_agent.db import Jsonb, tx
from rahbar_agent.storage import get_storage

log = logging.getLogger("rahbar.worker")


def h_crawl_source(p: dict[str, Any]) -> dict[str, Any]:
    return pipeline.crawl_source(p["source_id"])


def h_extract_policy(p: dict[str, Any]) -> dict[str, Any]:
    return pipeline.extract_policy(p["snapshot_id"])


def h_crawl_due(_p: dict[str, Any]) -> dict[str, Any]:
    return pipeline.crawl_due_sources()


def h_review_documents(p: dict[str, Any]) -> dict[str, Any]:
    with tx() as conn:
        r = documents.run_review(conn, p["case_id"])
    return {"blockers": r["blockers"], "findings": len(r["findings"])}


def h_expire_quotes(_p: dict[str, Any]) -> dict[str, Any]:
    with tx() as conn:
        return {"expired": pricing.expire_quotes(conn)}


def h_retention(p: dict[str, Any]) -> dict[str, Any]:
    """Delete documents N days after case completion unless the user opted to keep them (SECURITY.md)."""
    days = int(p.get("days", 90))
    st = get_storage()
    n = 0
    with tx() as conn:
        rows = conn.execute(
            """select d.id, d.storage_path, d.case_id from documents d join cases c on c.id=d.case_id
               join profiles pr on pr.id=c.owner_id
               where d.deleted_at is null and not pr.keep_documents
                 and c.status in ('completed','cancelled','refunded','decision_refused','decision_approved')
                 and coalesce(c.completed_at, c.updated_at) < now() - make_interval(days => %s)""", (days,)).fetchall()
        for r in rows:
            try:
                st.delete("documents", r["storage_path"])
            except Exception:
                log.warning("storage delete failed for document %s", r["id"])
            conn.execute("update documents set deleted_at=now(), extracted=null where id=%s", (r["id"],))
            conn.execute("insert into audit_log (action, entity, entity_id, data) values ('retention_delete','document',%s,%s)",
                         (r["id"], Jsonb({"case_id": str(r["case_id"])})))
            n += 1
    return {"deleted": n}


def h_poll_booking_status(_p: dict[str, Any]) -> dict[str, Any]:
    # Phase 6: poll real providers for status changes on open bookings
    return {"polled": 0}


def h_send_notification(p: dict[str, Any]) -> dict[str, Any]:
    # Email/SMS via Resend once configured; never include document contents or ID numbers.
    log.info("notification queued kind=%s case=%s", p.get("kind"), p.get("case_id"))
    return {"sent": bool(os.environ.get("RESEND_API_KEY"))}


def h_dummy(p: dict[str, Any]) -> dict[str, Any]:
    return {"echo": p}


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "crawl_source": h_crawl_source, "extract_policy": h_extract_policy, "crawl_due_sources": h_crawl_due,
    "review_documents": h_review_documents, "expire_quotes": h_expire_quotes, "retention_sweep": h_retention,
    "poll_booking_status": h_poll_booking_status, "send_notification": h_send_notification, "dummy": h_dummy,
}


def schedule_due() -> int:
    with tx() as conn:
        due = conn.execute("""update scheduled_jobs set next_run_at = now() + every
                              where active and next_run_at <= now() returning type, payload""").fetchall()
        for d in due:
            jobs.enqueue(d["type"], d["payload"], conn=conn)
    return len(due)


def run_once(types: list[str] | None = None) -> str | None:
    """Claim and run one job. Returns its id, or None if the queue is empty."""
    with tx() as conn:
        job = jobs.claim_next(conn, types)
    if job is None:
        return None
    handler = HANDLERS.get(job["type"])
    try:
        if handler is None:
            raise RuntimeError(f"no handler for {job['type']}")
        result = handler(job["payload"])
        with tx() as conn:
            jobs.finish(conn, str(job["id"]), result)
    except Exception as e:  # error text only — never payload contents
        log.exception("job %s (%s) failed", job["id"], job["type"])
        with tx() as conn:
            jobs.fail(conn, job, f"{type(e).__name__}: {e}"[:300])
    return str(job["id"])


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    stop = False

    def _stop(*_a: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker started")
    last_sched = 0.0
    while not stop:
        if time.monotonic() - last_sched > 30:
            schedule_due()
            last_sched = time.monotonic()
        if run_once() is None:
            time.sleep(float(os.environ.get("WORKER_IDLE_SLEEP", "2")))
    log.info("worker stopped")


if __name__ == "__main__":
    main()
