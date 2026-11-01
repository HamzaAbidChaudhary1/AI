"""Intent routing + slot extraction. Deterministic rules first; the fast model refines when available."""

from __future__ import annotations

import re
from typing import Any

from ..guardrails import is_fraud_request
from ..i18n import VISA_TYPES
from ..llm import LLMRefused, LLMUnavailable, get_llm
from ..scam import COUNTRY_WORDS, amounts_pkr

INTENTS = ["smalltalk", "quick_answer", "consult", "assess_eligibility", "build_quote", "scam_check", "plan_umrah",
           "booking_flow", "work_visa", "fraud_request", "refusal_analysis"]

_RX = {
    "scam_check": r"\bscam|fraud|agent (?:told|said|offered|is asking)|is (?:this|it) (?:real|legit|genuine)|asli|farzi|dhoka|"
                  r"فراڈ|دھوکہ|ایجنٹ نے|guarantee|100\s*%",
    "plan_umrah": r"umrah|عمرہ|makkah|madinah|مکہ|مدینہ",
    "booking_flow": r"\bflights?\b|\bticket|\bfly\b|airline|\bhotels?\b|فلائٹ|ٹکٹ|ہوٹل",
    "work_visa": r"work\s*visa|job\s*(?:visa|abroad)|naukri|ورک ویزا|نوکری|work permit",
    "build_quote": r"\bquote\b|price|cost (?:me|of using)|how much (?:will|do) (?:you|it)|kitne paise|قیمت|کتنا خرچ",
    "assess_eligibility": r"chances?|eligib|will i get|can i get|qualify|strong|weak|approval odds|chance hai|"
                          r"ملے گا|امکان|اہل",
    "refusal_analysis": r"refus|reject|mustarad|مسترد|انکار",
    "quick_answer": r"what (?:do|does|documents?|is|are)|requirement|documents?|fee|fees|how long|processing|need|"
                    r"kya chahiye|kaghzat|دستاویز|فیس|ضرورت|کیا چاہیے|کتنا وقت|visa",
}
_GREETING = r"^\s*(hi|hello|salam|assalam|aoa|hey|السلام|سلام)\b"


def detect_destination(text: str) -> str | None:
    for code, rx in COUNTRY_WORDS.items():
        if re.search(rx, text, re.IGNORECASE):
            return code
    return None


def extract_slots(text: str) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    dest = detect_destination(text)
    if dest:
        slots["destination"] = dest
        if dest in VISA_TYPES:
            slots["visa_type"] = VISA_TYPES[dest]
    if re.search(r"parents|mother and father|ammi abbu|walidain|والدین|امی ابو", text, re.IGNORECASE):
        slots["travellers"] = 2
        slots["for_whom"] = "parents"
    m = re.search(r"(\d+)\s*(?:people|persons|travell?ers|adults|afrad|افراد)", text, re.IGNORECASE)
    if m:
        slots["travellers"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(days?|weeks?|din|دن|ہفتے)", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        slots["days"] = n * 7 if m.group(2).lower().startswith(("week", "ہفت")) else n
    if amounts_pkr(text):
        slots["amounts_pkr"] = amounts_pkr(text)
    return slots


def classify_rules(text: str, payload: dict[str, Any]) -> str:
    if payload.get("profile"):
        return "assess_eligibility"
    if payload.get("action") in ("search_flights", "search_hotels", "select_offer"):
        return "booking_flow"
    if payload.get("action") == "umrah_options":
        return "plan_umrah"
    if payload.get("action") == "build_quote":
        return "build_quote"
    if is_fraud_request(text):
        return "fraud_request"
    t = text.strip()
    if not t:
        return "smalltalk"
    for intent in ("scam_check", "work_visa", "plan_umrah", "booking_flow", "refusal_analysis", "build_quote",
                   "assess_eligibility", "quick_answer"):
        if re.search(_RX[intent], t, re.IGNORECASE):
            if intent == "scam_check" and not re.search(r"agent|scam|fraud|offer|told|farzi|dhoka|فراڈ|ایجنٹ|دھوکہ", t, re.IGNORECASE):
                continue  # a bare '100%' or 'guarantee' question is not a scam check
            return intent
    if re.search(_GREETING, t, re.IGNORECASE) or len(t) < 12:
        return "smalltalk"
    return "consult"


ROUTER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"intent": {"type": "string", "enum": INTENTS},
                   "destination": {"type": ["string", "null"], "description": "ISO country code"},
                   "travellers": {"type": ["integer", "null"]}, "days": {"type": ["integer", "null"]}},
    "required": ["intent", "destination", "travellers", "days"],
}


def route(text: str, payload: dict[str, Any], history: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    intent = classify_rules(text, payload)
    slots = extract_slots(text)
    hard = intent in ("fraud_request",) or payload  # deterministic routes are never overridden
    llm = get_llm()
    if llm is not None and not hard and text.strip():
        try:
            recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-6:])
            r = llm.json("fast",
                         "Classify the user's latest message for a Pakistani travel & visa agency. "
                         "Input may be English, Urdu or Roman Urdu. Destination as ISO-3166 alpha-2 or null.",
                         f"Recent conversation:\n{recent}\n\nLatest message:\n{text}", ROUTER_SCHEMA, node="router",
                         max_tokens=1000)
            intent = r["intent"]
            for k in ("destination", "travellers", "days"):
                if r.get(k) and k not in slots:
                    slots[k] = r[k]
            if slots.get("destination") in VISA_TYPES:
                slots.setdefault("visa_type", VISA_TYPES[slots["destination"]])
        except (LLMUnavailable, LLMRefused, ValueError, KeyError):
            pass
    return intent, slots


def parse_profile_text(text: str) -> dict[str, Any]:
    """Best-effort profile hints from free text (offline). The UI profile form is the reliable path."""
    p: dict[str, Any] = {}
    t = text.lower()
    if re.search(r"\b(retired|pension|ریٹائر)", t):
        p["employment_status"] = "retired"
    elif re.search(r"\b(business|karobar|shop|کاروبار)", t):
        p["employment_status"] = "business_owner"
    elif re.search(r"\b(job|employed|naukri|work at|ملازمت)", t):
        p["employment_status"] = "employed"
    elif re.search(r"\b(unemployed|no job|berozgar|بے روزگار)", t):
        p["employment_status"] = "unemployed"
    elif re.search(r"\b(student|طالب علم)", t):
        p["employment_status"] = "student"
    am = amounts_pkr(text)
    if am and re.search(r"saving|balance|bank|account|funds|بینک|بچت", t):
        p["funds_available_minor"] = max(am) * 100
    hist = [c for c, rx in COUNTRY_WORDS.items() if re.search(rf"(visited|been to|went to|travelled to)\s+(?:{rx})", t)]
    if hist:
        p["travel_history"] = [{"country": c} for c in hist]
    if re.search(r"refus|reject|مسترد", t):
        dest = detect_destination(text)
        p["prior_refusals"] = [{"country": dest or "XX"}]
    return p
