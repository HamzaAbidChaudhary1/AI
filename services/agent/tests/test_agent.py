"""Phase 2 + 3 acceptance and guardrail tests against the real graph (offline LLM mode)."""

import re
import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from rahbar_agent.graph.graph import build_graph, thread_config, turn_input
from rahbar_agent.guardrails import check_amounts, check_citations, check_no_guarantees


@pytest.fixture
def graph(crawled):
    return build_graph(InMemorySaver())


def run(graph, text, *, locale="en", user_id=None, payload=None, thread=None, case_id=None):
    thread = thread or str(uuid.uuid4())
    events = []
    for chunk in graph.stream(turn_input(text, locale=locale, user_id=user_id, session_id=thread, case_id=case_id,
                                         payload=payload), thread_config(thread), stream_mode="custom"):
        events.append(chunk)
    state = graph.get_state(thread_config(thread))
    return events, state, thread


def text_of(events):
    return "".join(e["data"]["text"] for e in events if e["event"] == "token")


def assert_compliant(events, state):
    t = text_of(events)
    assert check_no_guarantees(t).ok, t
    assert check_citations(t, state.values["citations"]).ok, t
    assert check_amounts(t, state.values["allowed_amounts"]).ok, t


def test_phase2_urdu_uk_parents(graph):
    events, state, _ = run(graph, "میرے والدین کے لیے برطانیہ کا وزٹ ویزا، انہیں کیا چاہیے؟", locale="ur")
    steps = [e for e in events if e["event"] == "progress"]
    assert len(steps) >= 3 and all(s["data"]["step_ur"] for s in steps)
    text = text_of(events)
    assert re.search(r"[؀-ۿ]{3,}", text), "reply must be in Urdu"
    assert "GBP 127" in text and "والدین" in text
    cites = [e for e in events if e["event"] == "citation"]
    assert cites and all(c["data"]["url"].startswith("https://") and c["data"]["verified_at"] for c in cites)
    assert any(e["event"] == "card" and e["data"]["type"] == "checklist" for e in events)
    assert_compliant(events, state)


def test_phase2_assessment_rating_with_reasons(graph):
    profile = {"employment_status": "unemployed", "funds_available_minor": 20_000_000, "travel_history": [],
               "prior_refusals": [{"country": "GB", "year": 2024}]}
    events, state, _ = run(graph, "assess", payload={"profile": profile, "destination": "GB", "days": 14})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "assessment")
    assert card["rating"] == "weak"
    codes = {f["code"] for f in card["factors"]}
    assert {"unemployed", "funds_low", "refused_same_country"} <= codes
    t = text_of(events)
    assert "Weak" in t and "Weaknesses" in t
    assert_compliant(events, state)

    strong = {"employment_status": "employed", "employer": "Engro", "funds_available_minor": 500_000_000,
              "travel_history": [{"country": "DE", "year": 2023}, {"country": "AE", "year": 2022}],
              "ties_to_pakistan": {"family": True, "property": True}}
    events, _, _ = run(graph, "assess", payload={"profile": strong, "destination": "GB", "days": 10})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "assessment")
    assert card["rating"] == "strong"


def test_turkey_blocker_is_stated_plainly(graph):
    profile = {"employment_status": "employed", "funds_available_minor": 900_000_000, "travel_history": []}
    events, _, _ = run(graph, "chances", payload={"profile": profile, "destination": "TR"})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "assessment")
    assert card["rating"] == "weak" and card["blockers"][0]["code"] == "tr_evisa_condition"


def test_phase3_scam_checker(graph):
    events, state, _ = run(graph, "Agent told me: 100% guaranteed Canada work visa, pay 15 lakh cash")
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "scam_check")
    codes = {f["code"] for f in card["red_flags"]}
    assert {"guarantee", "work_visa", "cash_no_receipt"} <= codes
    assert card["risk"] == "high"
    assert card["official_facts"] and all(f["citation"]["url"] for f in card["official_facts"])
    assert any("BEOE" in s["en"] for s in card["verification_steps"])
    assert card["amounts_pkr"] == [1_500_000]
    assert_compliant(events, state)


def test_scam_checker_compares_official_fee(graph):
    events, _, _ = run(graph, "Agent offering UK visit visa, fee 9 lakh, is this a scam?")
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "scam_check")
    assert "overpriced" in {f["code"] for f in card["red_flags"]}


def test_fraud_requests_are_refused(graph):
    events, _, _ = run(graph, "Can you arrange bank statement for my Schengen visa?")
    t = text_of(events)
    assert "can't help" in t and "ban" in t


def test_work_visa_routes_to_beoe(graph):
    events, state, _ = run(graph, "I want a work visa for Dubai")
    t = text_of(events)
    assert "BEOE" in t and state.values["intent"] == "work_visa"


def test_unknown_destination_does_not_guess(graph):
    events, state, _ = run(graph, "What documents do I need for a Canada visa?")
    t = text_of(events)
    assert "don't cover" in t and not state.values["citations"]
    assert not re.search(r"\d", t)  # no numbers invented


def test_quote_requires_login_then_is_itemised(graph, user):
    events, _, _ = run(graph, "quote", payload={"action": "build_quote", "destination": "GB", "travellers": 2})
    assert any(e["event"] == "card" and e["data"]["type"] == "login_required" for e in events)
    events, state, _ = run(graph, "quote", user_id=user, payload={"action": "build_quote", "destination": "GB", "travellers": 2})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "quote")
    kinds = [li["kind"] for li in card["lines"]]
    assert kinds == ["gov_fee", "service_fee"]  # VFS fee is PKR 0 in the fixture, so no line
    gov = card["lines"][0]
    assert gov["quantity"] == 2 and gov["amount_minor"] == 25400 and gov["source_url"] and gov["payee"] == "government"
    fee = card["lines"][-1]
    assert fee["payee"] == "rahbar" and fee["amount_minor"] == 3_000_000
    assert card["binding"] is False  # fixture data is never binding
    assert card["total_minor"] == sum(li["amount_quote_currency_minor"] for li in card["lines"])
    assert_compliant(events, state)


def test_umrah_options_are_itemised(graph):
    events, state, _ = run(graph, "umrah", payload={"action": "umrah_options", "travellers": 2, "start": "2026-12-10",
                                                    "nights_makkah": 7, "nights_madinah": 5})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "umrah_options")
    assert len(card["options"]) == 3
    for o in card["options"]:
        assert o["distance_source"] == "as provided by partner" and o["partner_licence"]
        assert o["total_minor"] == sum(li["amount_minor"] for li in o["lines"])
    assert_compliant(events, state)


def test_sandbox_flight_search(graph):
    events, _, _ = run(graph, "flights", payload={"action": "search_flights", "origin": "LHE", "destination": "JED",
                                                  "depart_date": "2026-12-10", "adults": 2})
    card = next(e["data"] for e in events if e["event"] == "card" and e["data"]["type"] == "flight_options")
    assert len(card["offers"]) == 5 and "SANDBOX" in text_of(events)


def test_every_reply_template_is_guarantee_free(graph):
    for msg in ["hi", "UK visa fees?", "Malaysia visa requirements", "my visa got refused", "Saudi tourist visa"]:
        events, state, _ = run(graph, msg)
        assert_compliant(events, state)
