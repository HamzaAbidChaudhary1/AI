"""Phase 1 acceptance: changing a fixture page creates a new snapshot, an updated policy record
and an ops review task. Plus freshness rules and the domain allow-list."""

from datetime import UTC, datetime, timedelta

import pytest
from rahbar_agent import knowledge
from rahbar_agent.crawl import pipeline
from rahbar_agent.crawl.extract import extract_offline
from rahbar_agent.crawl.providers import FixtureProvider, domain_allowed, fixture_path, set_crawl_provider

UK = "https://www.gov.uk/standard-visitor"


@pytest.fixture
def fixtures():
    p = FixtureProvider()
    set_crawl_provider(p)
    yield p
    set_crawl_provider(None)


def _source_id(db, url):
    return str(db.fetch_one("select id from sources where url=%s", (url,))["id"])


def test_allow_list():
    allowed = ["gov.uk", "vfsglobal.com"]
    assert domain_allowed("https://www.gov.uk/standard-visitor", allowed)
    assert domain_allowed("https://visa.vfsglobal.com/pak/en/gbr", allowed)
    assert not domain_allowed("https://gov.uk.evil.com/x", allowed)
    assert not domain_allowed("http://www.gov.uk/x", allowed)  # https only
    assert not domain_allowed("https://notgov.uk/x", allowed)


def test_offline_extractor_never_infers():
    fields = extract_offline("# Page\nSome text about fees but no explicit label.\n")
    assert all(v is None for v in fields.values())
    f = extract_offline(fixture_path(UK).read_text())
    assert f["gov_fee"]["currency"] == "GBP" and f["gov_fee"]["amount"] == 127
    assert f["max_stay"]["days"] == 180
    assert len(f["required_documents"]) >= 5


def _private_source(db, fixtures, base_url, country):
    """A dedicated source row so this test is independent of other tests' crawls."""
    import uuid

    url = f"https://www.gov.uk/test-{uuid.uuid4().hex[:8]}"
    fixtures.overrides[url] = fixture_path(base_url).read_text()
    row = db.fetch_one("""insert into sources (url, title, authority, country, topic, visa_type)
                          values (%s,'Test page','gov.uk',%s,'visit_visa','visitor') returning id""", (url, country))
    return str(row["id"]), url


def test_crawl_change_detection_creates_review_task(db, fixtures):
    sid, url = _private_source(db, fixtures, UK, "ZQ")
    first = pipeline.crawl_source(sid, extract_inline=True)
    assert first["changed"] is True
    facts = knowledge.get_policy("ZQ", "visitor", ["gov_fee"])
    assert facts["gov_fee"].value["amount_minor"] == 12700
    assert facts["gov_fee"].citation.is_test_fixture is True
    assert facts["gov_fee"].usable_in_quote is False  # fixture data never goes into a binding quote

    # unchanged page: no new snapshot, but freshness advances
    again = pipeline.crawl_source(sid, extract_inline=True)
    assert again["changed"] is False and again["snapshot_id"] == first["snapshot_id"]

    # the page changes: fee goes up
    fixtures.overrides[url] = fixture_path(UK).read_text().replace("GBP 127", "GBP 135")
    changed = pipeline.crawl_source(sid, extract_inline=True)
    assert changed["changed"] is True and changed["snapshot_id"] != first["snapshot_id"]
    assert "gov_fee" in changed["extract"]["changed_fields"]

    snaps = db.fetch_all("select changed_from_previous from source_snapshots where source_id=%s order by fetched_at", (sid,))
    assert [s["changed_from_previous"] for s in snaps] == [False, True]
    facts = knowledge.get_policy("ZQ", "visitor", ["gov_fee"])
    assert facts["gov_fee"].value["amount_minor"] == 13500
    recs = db.fetch_all("""select pr.value->>'amount_minor' a, pr.status from policy_records pr
                           join source_snapshots s on s.id=pr.source_snapshot_id
                           where s.source_id=%s and pr.field='gov_fee' order by pr.created_at""", (sid,))
    assert [(r["a"], r["status"]) for r in recs] == [("12700", "stale"), ("13500", "auto")]
    task = db.fetch_one("select * from ops_tasks where kind='policy_change_review' order by created_at desc limit 1")
    assert task["payload"]["old"]["amount_minor"] == 12700 and task["payload"]["new"]["amount_minor"] == 13500
    assert facts["gov_fee"].fresh


def test_freshness_windows():
    now = datetime.now(UTC)
    assert knowledge.is_fresh("gov_fee", now - timedelta(days=6), now)
    assert not knowledge.is_fresh("gov_fee", now - timedelta(days=8), now)
    assert knowledge.is_fresh("max_stay", now - timedelta(days=29), now)
    assert not knowledge.is_fresh("max_stay", now - timedelta(days=31), now)
    assert knowledge.usable_in_quote("verified", now - timedelta(days=60), False, now)
    assert knowledge.usable_in_quote("auto", now - timedelta(days=6), False, now)
    assert not knowledge.usable_in_quote("auto", now - timedelta(days=8), False, now)
    assert not knowledge.usable_in_quote("verified", now, True, now)


def test_stale_policy_triggers_live_fetch(db, fixtures):
    sid = _source_id(db, "https://www.evisa.gov.tr/en/")
    pipeline.crawl_source(sid, extract_inline=True)
    db.execute("update source_snapshots set last_seen_at = now() - interval '20 days' where source_id=%s", (sid,))
    assert not knowledge.get_policy("TR", "evisa", ["gov_fee"])["gov_fee"].fresh
    steps = []
    facts, unverified = knowledge.ensure_fresh_policy("TR", "evisa", ["gov_fee"], progress=lambda *a: steps.append(a))
    assert facts["gov_fee"].fresh and unverified == [] and steps


def test_live_fetch_refuses_non_allowlisted(db, fixtures):
    assert knowledge.live_fetch("https://evil-visa-agent.example.com/fees") == {"ok": False, "error": "domain_not_allowed"}


def test_fts_and_licence_lookup(db, fixtures):
    pipeline.crawl_source(_source_id(db, "https://beoe.gov.pk/"))
    hits = knowledge.search_snapshots("licensed promoters receipt")
    assert hits and hits[0]["citation"]["authority"] == "beoe.gov.pk"
    found = knowledge.verify_agent_licence("1234/RWP")
    assert found["found"] and found["status"] == "Valid"
    suspended = knowledge.verify_agent_licence("Sea Gate")
    assert suspended["status"] == "Suspended"
    assert knowledge.verify_agent_licence("Fake Visa Kings")["found"] is False


def test_crawl_due_enqueues_jobs(db, fixtures):
    _private_source(db, fixtures, UK, "ZR")  # never crawled -> due
    r = pipeline.crawl_due_sources()
    assert r["enqueued"] > 0
    assert pipeline.crawl_due_sources()["enqueued"] == 0  # not double-enqueued


def test_missing_fields_do_not_trigger_refetch(db, fixtures):
    sid = _source_id(db, "https://malaysiavisa.imi.gov.my/evisa/evisa.jsp")
    pipeline.crawl_source(sid, extract_inline=True)
    steps = []
    knowledge.ensure_fresh_policy("MY", "evisa", ["gov_fee", "interview_required"], progress=lambda *a: steps.append(a))
    assert steps == []  # interview_required isn't on the page; nothing is stale
