"""crawl_source -> snapshot (on change) -> extract_policy -> policy_records (+ ops review on change)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from psycopg import Connection

from .. import jobs
from ..db import Jsonb, tx
from .extract import extract_policy_fields, normalise_value
from .providers import CrawlError, domain_allowed, get_crawl_provider

log = logging.getLogger(__name__)


def content_hash(markdown: str) -> str:
    # normalise whitespace so cosmetic re-renders don't count as policy changes
    norm = "\n".join(line.strip() for line in markdown.strip().splitlines() if line.strip())
    return hashlib.sha256(norm.encode()).hexdigest()


def allowed_domains(conn: Connection) -> list[str]:
    return [r["domain"] for r in conn.execute("select domain from allowed_domains")]


def store_snapshot(conn: Connection, source: dict[str, Any], markdown: str, http_status: int,
                   provider: str) -> tuple[dict[str, Any], bool]:
    """Insert a snapshot if content changed; otherwise bump last_seen_at. Returns (snapshot, changed)."""
    h = content_hash(markdown)
    prev = conn.execute(
        "select * from source_snapshots where source_id=%s order by fetched_at desc limit 1", (source["id"],)
    ).fetchone()
    if prev and prev["content_hash"] == h:
        conn.execute("update source_snapshots set last_seen_at=now(), http_status=%s where id=%s",
                     (http_status, prev["id"]))
        snap = conn.execute("select * from source_snapshots where id=%s", (prev["id"],)).fetchone()
        return snap, False
    snap = conn.execute(
        """insert into source_snapshots (source_id, content_markdown, content_hash, http_status,
                                         changed_from_previous, provider)
           values (%s, %s, %s, %s, %s, %s) returning *""",
        (source["id"], markdown, h, http_status, prev is not None, provider),
    ).fetchone()
    return snap, True


def crawl_source(source_id: str, *, extract_inline: bool = False) -> dict[str, Any]:
    with tx() as conn:
        source = conn.execute("select * from sources where id=%s", (source_id,)).fetchone()
        if source is None:
            raise ValueError("unknown source")
        if not domain_allowed(source["url"], allowed_domains(conn)):
            raise CrawlError(f"domain not on allow-list: {source['url']}")
    provider = get_crawl_provider()
    try:
        res = provider.fetch(source["url"], actor=source.get("apify_actor"), prefer=source["crawl_method"])
    except CrawlError as e:
        with tx() as conn:
            conn.execute("update sources set last_crawled_at=now(), last_crawl_status=%s where id=%s",
                         (f"error: {e}"[:200], source_id))
        raise
    with tx() as conn:
        snap, changed = store_snapshot(conn, source, res.markdown, res.http_status, res.provider)
        conn.execute("update sources set last_crawled_at=now(), last_crawl_status='ok' where id=%s", (source_id,))
        job_id = None
        if changed and source.get("visa_type") and source.get("country") and not extract_inline:
            job_id = jobs.enqueue("extract_policy", {"snapshot_id": str(snap["id"])}, conn=conn)
    result: dict[str, Any] = {"snapshot_id": str(snap["id"]), "changed": changed, "extract_job": job_id}
    if changed and extract_inline and source.get("visa_type") and source.get("country"):
        result["extract"] = extract_policy(str(snap["id"]))
    return result


def extract_policy(snapshot_id: str) -> dict[str, Any]:
    with tx() as conn:
        row = conn.execute(
            """select s.*, src.country, src.visa_type, src.id as src_id, src.url
               from source_snapshots s join sources src on src.id = s.source_id where s.id=%s""",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise ValueError("unknown snapshot")
    fields, method = extract_policy_fields(row["content_markdown"], row["country"], row["visa_type"])
    changed_fields: list[str] = []
    with tx() as conn:
        for field, raw in fields.items():
            value = normalise_value(field, raw)
            if value is None:
                continue
            current = conn.execute(
                """select pr.* from policy_records pr join source_snapshots s on s.id = pr.source_snapshot_id
                   where pr.country=%s and pr.visa_type=%s and pr.field=%s and s.source_id=%s
                     and pr.status in ('auto','verified')
                   order by pr.created_at desc limit 1""",
                (row["country"], row["visa_type"], field, row["src_id"]),
            ).fetchone()
            if current and current["value"] == value:
                # same fact, newer evidence: move the record onto the new snapshot (keeps verified status)
                conn.execute("update policy_records set source_snapshot_id=%s where id=%s", (snapshot_id, current["id"]))
                continue
            new = conn.execute(
                """insert into policy_records (country, visa_type, field, value, source_snapshot_id, status)
                   values (%s,%s,%s,%s,%s,'auto') returning id""",
                (row["country"], row["visa_type"], field, Jsonb(value), snapshot_id),
            ).fetchone()
            if current:
                conn.execute("update policy_records set status='stale' where id=%s", (current["id"],))
                conn.execute(
                    """insert into ops_tasks (kind, policy_record_id, payload)
                       values ('policy_change_review', %s, %s)""",
                    (new["id"], Jsonb({"field": field, "country": row["country"], "visa_type": row["visa_type"],
                                       "old": current["value"], "new": value, "url": row["url"],
                                       "old_record_id": str(current["id"])})),
                )
                changed_fields.append(field)
    if changed_fields:
        log.info("policy change detected", extra={"fields": changed_fields, "snapshot": snapshot_id})
    return {"method": method, "changed_fields": changed_fields,
            "extracted": sorted(k for k, v in fields.items() if v is not None)}


def crawl_due_sources() -> dict[str, Any]:
    """Scheduler entry: enqueue crawl jobs for sources whose crawl_frequency has elapsed."""
    with tx() as conn:
        due = conn.execute(
            """select id from sources where active and
                 (last_crawled_at is null or last_crawled_at + crawl_frequency <= now())
                 and not exists (select 1 from jobs j where j.type='crawl_source' and j.status in ('queued','running')
                                 and j.payload->>'source_id' = sources.id::text)"""
        ).fetchall()
        for r in due:
            jobs.enqueue("crawl_source", {"source_id": str(r["id"])}, conn=conn)
    return {"enqueued": len(due)}
