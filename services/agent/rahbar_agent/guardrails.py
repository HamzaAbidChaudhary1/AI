"""Guardrails enforced in code (CLAUDE.md non-negotiable rules 1, 2, 5).

* guarantee-language validator for every outbound text (agent replies, emails, templates)
* citation validator: policy/fee claims must be backed by tool-result citations
* amounts validator: any money amount in a reply must come from a tool result
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# Phrases that promise an outcome. English, Urdu and Roman Urdu.
GUARANTEE_PATTERNS: list[str] = [
    r"guarantee[ds]?",
    r"guaranteeing",
    r"100\s*%",
    r"100\s*percent",
    r"hundred\s+percent",
    r"confirm(?:ed)?\s+visa",
    r"visa\s+(?:is\s+)?confirm(?:ed)?",
    r"sure[\s-]*shot",
    r"assured\s+(?:visa|approval)",
    r"(?:visa|approval)\s+(?:is\s+)?assured",
    r"definitely\s+(?:get|be\s+approved|approved)",
    r"will\s+(?:surely|definitely|certainly)\s+(?:get|be)",
    r"no\s+chance\s+of\s+(?:refusal|rejection)",
    r"pakk[ai]\s+visa",
    r"visa\s+pakk[ai]",
    r"yaqeeni",
    # Urdu script
    r"گارنٹی",
    r"گارنٹیڈ",
    r"یقینی\s*ویزا",
    r"ویزا\s*یقینی",
    r"پکا\s*ویزا",
    r"ویزا\s*پکا",
    r"سو\s*فیصد",
    r"١٠٠\s*٪",
    r"100\s*٪",
    r"ضمانت",
]

NEGATIONS_EN = (
    r"\bnot\b", r"\bno\b", r"\bnever\b", r"\bcannot\b", r"\bcan't\b", r"\bcan’t\b", r"\bnobody\b",
    r"\bno one\b", r"\bdon't\b", r"\bdon’t\b", r"\bdoesn't\b", r"\bdoesn’t\b", r"\bwon't\b", r"\bisn't\b",
    r"\bimpossible\b", r"\bfake\b", r"\bscam\b", r"\bred flag\b", r"\bclaim(?:s|ed|ing)?\b", r"\bpromised\b", r"\bthey\s+(?:say|said|told)\b",
    r"\bnahi\b", r"\bnahin\b",
)
NEGATIONS_UR = ("نہیں", "نہ ", "کوئی بھی", "ناممکن", "جھوٹ", "فراڈ", "دھوکہ", "دعوی", "دعویٰ")

_QUOTE_RE = re.compile(r"[\"“”«»‘’']([^\"“”«»‘’']{1,200})[\"“”«»‘’']")
_GUARANTEE_RE = re.compile("|".join(f"(?:{p})" for p in GUARANTEE_PATTERNS), re.IGNORECASE)


@dataclass
class GuardrailResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def _strip_quotes(text: str) -> str:
    """Quoted material (e.g. what a scam agent said) is reported speech, not our claim."""
    return _QUOTE_RE.sub(" ", text)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?؟۔\n])\s+", text) if s.strip()]


_AFTER_NEG_EN = re.compile(
    r"^.{0,40}?(\b(?:is|are|was)\s+(?:not|never)\b|\bimpossible\b|\bscam\b|\bfake\b|\bred flag\b|\bfraud\b)",
    re.IGNORECASE,
)


def _negated(sentence: str, match_start: int) -> bool:
    before = sentence[max(0, match_start - 60) : match_start].lower()
    if any(re.search(n, before) for n in NEGATIONS_EN):
        return True
    if _AFTER_NEG_EN.search(sentence[match_start:]):
        return True
    return any(n in sentence for n in NEGATIONS_UR)


def find_guarantee_language(text: str, allow_negated: bool = True) -> list[str]:
    """Returns offending snippets. Negated statements ("no one can guarantee a visa") and
    quoted reported speech are allowed when allow_negated=True; templates use False."""
    hits: list[str] = []
    body = _strip_quotes(text) if allow_negated else text
    for sentence in _sentences(body):
        for m in _GUARANTEE_RE.finditer(sentence):
            if allow_negated and _negated(sentence, m.start()):
                continue
            hits.append(sentence.strip()[:160])
            break
    return hits


def check_no_guarantees(text: str, allow_negated: bool = True) -> GuardrailResult:
    hits = find_guarantee_language(text, allow_negated=allow_negated)
    return GuardrailResult(ok=not hits, violations=[f"guarantee language: {h}" for h in hits])


# ---------------------------------------------------------------------------- amounts & citations

_CCY = r"(?:PKR|Rs\.?|USD|US\$|\$|SAR|EUR|€|GBP|£|AED|TRY|MYR|روپے)"
_NUM = r"\d[\d,]*(?:\.\d+)?"
_MONEY_RE = re.compile(rf"(?:{_CCY}\s?{_NUM})|(?:{_NUM}\s?{_CCY})", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

FACT_KEYWORDS = re.compile(
    r"\b(fee|fees|cost|costs|price|charge|processing time|working days|validity|valid for|max(?:imum)? stay|"
    r"required documents?|requirement|proof of funds|bank statement must|biometrics?)\b|فیس|قیمت|ضروری دستاویزات|مدت",
    re.IGNORECASE,
)


def money_mentions(text: str) -> list[str]:
    return [m.group(0) for m in _MONEY_RE.finditer(text)]


def _norm_number(s: str) -> str:
    m = _DIGITS_RE.search(s)
    if not m:
        return ""
    n = m.group(0).replace(",", "")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n


def check_amounts(text: str, allowed_amounts: Iterable[str]) -> GuardrailResult:
    """Every money amount in the text must appear in tool results (rule 3: never invent a fee)."""
    allowed = {_norm_number(a) for a in allowed_amounts}
    bad = [m for m in money_mentions(text) if _norm_number(m) not in allowed]
    return GuardrailResult(ok=not bad, violations=[f"amount not from a tool result: {b}" for b in bad])


def check_citations(text: str, citations: list[dict]) -> GuardrailResult:
    """Policy/fee/requirement claims need at least one citation with url + verified_at."""
    if not FACT_KEYWORDS.search(_strip_quotes(text)) and not money_mentions(text):
        return GuardrailResult(ok=True)
    valid = [c for c in citations if c.get("url") and c.get("verified_at")]
    if not valid:
        return GuardrailResult(ok=False, violations=["factual claim without a cited official source"])
    return GuardrailResult(ok=True)


def validate_reply(text: str, citations: list[dict], allowed_amounts: Iterable[str]) -> GuardrailResult:
    """Post-processing validator run on every agent reply before it is streamed."""
    results = [check_no_guarantees(text), check_citations(text, citations), check_amounts(text, allowed_amounts)]
    violations = [v for r in results for v in r.violations]
    return GuardrailResult(ok=not violations, violations=violations)


# ---------------------------------------------------------------------------- dishonesty requests

FRAUD_REQUEST_RE = re.compile(
    r"(fake|forged?|dummy|edit(?:ed)?|fabricat\w*|photoshop\w*|arrange(?:d)?)\s+(bank\s+statement|balance|"
    r"funds|employment\s+letter|job\s+letter|sponsor\w*|noc|salary\s+slip|documents?|ticket|hotel\s+booking)|"
    r"(bank\s+statement|balance)\s+(bana|banwa|edit|increase\s+temporarily)|"
    r"jaali|jali\s+(documents?|statement)|جعلی|نقلی",
    re.IGNORECASE,
)


def is_fraud_request(text: str) -> bool:
    return bool(FRAUD_REQUEST_RE.search(text))
