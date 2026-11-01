"""Knowledge tools (docs/AGENT.md "Tools > Knowledge") + freshness rules (docs/CRAWLING.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from .config import get_settings
from .crawl.extract import FEE_REQUIREMENT_FIELDS
from .crawl.pipeline import allowed_domains, crawl_source, store_snapshot
from .crawl.providers import CrawlError, domain_allowed, get_crawl_provider
from .db import tx


class Citation(BaseModel):
    url: str
    title: str
    authority: str
    verified_at: str            # ISO timestamp: last time we saw this exact content
    is_test_fixture: bool = False

    def key(self) -> str:
        return self.url


class PolicyFact(BaseModel):
    field: str
    value: Any
    status: str                 # auto | verified
    fresh: bool
    citation: Citation
    usable_in_quote: bool       # CRAWLING.md: verified, or auto + fresh <= 7 days, never fixture


def max_age_days(field: str) -> int:
    s = get_settings()
    return s.fresh_days_fees if field in FEE_REQUIREMENT_FIELDS else s.fresh_days_general


def is_fresh(field: str, seen_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return now - seen_at <= timedelta(days=max_age_days(field))


def usable_in_quote(status: str, seen_at: datetime, is_fixture: bool, now: datetime | None = None) -> bool:
    if is_fixture:
        return False
    now = now or datetime.now(UTC)
    if status == "verified":
        return True
    return status == "auto" and now - seen_at <= timedelta(days=get_settings().fresh_days_fees)


def _citation(row: dict[str, Any]) -> Citation:
    return Citation(
        url=row["url"], title=row["title"] or row["url"], authority=row["authority"],
        verified_at=row["last_seen_at"].astimezone(UTC).isoformat(),
        is_test_fixture=row["provider"] == "fixture",
    )


def get_policy(country: str, visa_type: str, fields: list[str] | None = None) -> dict[str, PolicyFact]:
    """Best current record per field: verified beats auto, then most recently seen."""
    with tx() as conn:
        rows = conn.execute(
            """select distinct on (pr.field)
                      pr.field, pr.value, pr.status, s.last_seen_at, s.provider,
                      src.url, src.title, src.authority
               from policy_records pr
               join source_snapshots s on s.id = pr.source_snapshot_id
               join sources src on src.id = s.source_id
               where pr.country=%s and pr.visa_type=%s and pr.status in ('auto','verified')
                 and (%s::text[] is null or pr.field = any(%s))
               order by pr.field, (pr.status = 'verified') desc, s.last_seen_at desc""",
            (country, visa_type, fields, fields),
        ).fetchall()
    out: dict[str, PolicyFact] = {}
    for r in rows:
        out[r["field"]] = PolicyFact(
            field=r["field"], value=r["value"], status=r["status"],
            fresh=is_fresh(r["field"], r["last_seen_at"]), citation=_citation(r),
            usable_in_quote=usable_in_quote(r["status"], r["last_seen_at"], r["provider"] == "fixture"),
        )
    return out


def search_snapshots(query: str, country: str | None = None, topic: str | None = None,
                     limit: int = 5) -> list[dict[str, Any]]:
    """Postgres FTS over the latest snapshot of each source (no vectors in MVP)."""
    with tx() as conn:
        rows = conn.execute(
            """with latest as (
                 select distinct on (source_id) * from source_snapshots order by source_id, fetched_at desc)
               select src.url, src.title, src.authority, src.country, src.topic, l.last_seen_at, l.provider,
                      ts_rank(l.fts, q) as rank,
                      ts_headline('english', l.content_markdown, q,
                                  'MaxWords=45, MinWords=15, MaxFragments=2, StartSel="", StopSel=""') as excerpt
               from latest l join sources src on src.id = l.source_id,
                    websearch_to_tsquery('english', %s) q
               where l.fts @@ q and (%s::text is null or src.country = %s) and (%s::text is null or src.topic = %s)
               order by rank desc limit %s""",
            (query, country, country, topic, topic, limit),
        ).fetchall()
    return [{"excerpt": r["excerpt"], "country": r["country"], "topic": r["topic"],
             "citation": _citation(r).model_dump()} for r in rows]


def live_fetch(url: str) -> dict[str, Any]:
    """Firecrawl/Apify scrape of an allow-listed official domain only; stores a snapshot and re-extracts."""
    with tx() as conn:
        if not domain_allowed(url, allowed_domains(conn)):
            return {"ok": False, "error": "domain_not_allowed"}
        source = conn.execute("select * from sources where url=%s", (url,)).fetchone()
    if source is not None:
        try:
            res = crawl_source(str(source["id"]), extract_inline=True)
        except CrawlError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **res}
    # unknown but allow-listed URL: snapshot only (ops can register it as a source)
    try:
        page = get_crawl_provider().fetch(url)
    except CrawlError as e:
        return {"ok": False, "error": str(e)}
    with tx() as conn:
        src = conn.execute(
            """insert into sources (url, title, authority, topic, active) values (%s,%s,%s,'adhoc',false)
               on conflict (url) do update set url=excluded.url returning *""",
            (url, url, url.split("/")[2]),
        ).fetchone()
        snap, changed = store_snapshot(conn, src, page.markdown, page.http_status, page.provider)
    return {"ok": True, "snapshot_id": str(snap["id"]), "changed": changed}


def sources_for(country: str, visa_type: str | None = None) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute(
            "select * from sources where active and country=%s and (%s::text is null or visa_type=%s)",
            (country, visa_type, visa_type),
        ).fetchall()


def ensure_fresh_policy(country: str, visa_type: str, fields: list[str],
                        progress: Any = None) -> tuple[dict[str, PolicyFact], list[str]]:
    """The ensure_fresh_sources subgraph: stale/missing -> live_fetch the sources -> re-read.
    Returns (facts, unverified_fields). Unverified facts are still returned, marked not fresh."""
    facts = get_policy(country, visa_type, fields)
    missing_or_stale = [f for f in fields if f not in facts or not facts[f].fresh]
    if missing_or_stale:
        for src in sources_for(country, visa_type):
            if progress:
                progress("refetch", src["title"] or src["url"])
            live_fetch(src["url"])
        facts = get_policy(country, visa_type, fields)
    unverified = [f for f in fields if f in facts and not facts[f].fresh]
    return facts, unverified


def verify_agent_licence(name_or_number: str) -> dict[str, Any]:
    """Look up a promoter in the crawled BEOE list. Absence from our copy is NOT proof of fraud."""
    q = name_or_number.strip()
    with tx() as conn:
        rows = conn.execute(
            """with latest as (
                 select distinct on (source_id) * from source_snapshots order by source_id, fetched_at desc)
               select src.url, src.title, src.authority, l.last_seen_at, l.provider, l.content_markdown
               from latest l join sources src on src.id = l.source_id
               where src.authority = 'beoe.gov.pk'"""
        ).fetchall()
    for r in rows:
        for line in r["content_markdown"].splitlines():
            if q and q.lower() in line.lower() and line.strip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                return {"found": True, "row": cells, "status": cells[-1] if cells else None,
                        "citation": _citation(r).model_dump()}
    return {"found": False, "citation": _citation(rows[0]).model_dump() if rows else None}
