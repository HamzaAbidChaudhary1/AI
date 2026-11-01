"""Scam Checker (PRD J4): red flags, cited official facts, how to verify, CTA."""

from __future__ import annotations

import re
from typing import Any

from . import knowledge
from .i18n import VISA_TYPES, country_name
from .money import convert_minor, format_money

FLAGS: list[tuple[str, str, str, str]] = [
    # code, regex, en, ur
    ("guarantee", r"guarant\w*|100\s*%|hundred percent|sure[\s-]*shot|pakk[ai]\s+visa|گارنٹی|سو\s*فیصد|پکا\s*ویزا|confirm(?:ed)?\s+visa",
     "Claims to guarantee a visa. No agent can guarantee a visa — only the embassy decides. This is the most common scam line.",
     "ویزا کی گارنٹی کا دعویٰ۔ کوئی ایجنٹ ویزا کی گارنٹی نہیں دے سکتا — فیصلہ صرف سفارت خانہ کرتا ہے۔ یہ سب سے عام فراڈ جملہ ہے۔"),
    ("work_visa", r"work\s*(?:visa|permit)|job\s*visa|naukri|employment\s+visa|work\s+on\s+visit|ورک\s*ویزا|نوکری",
     "Offers a work visa or job abroad. Legal overseas employment from Pakistan goes only through BEOE-licensed promoters (OEPs), "
     "with Protector of Emigrants registration. A visit visa is never a work visa.",
     "بیرونِ ملک نوکری یا ورک ویزا کی پیشکش۔ پاکستان سے قانونی بیرونِ ملک ملازمت صرف (BEOE) کے لائسنس یافتہ پروموٹرز (OEP) "
     "اور پروٹیکٹر آف ایمیگرنٹس رجسٹریشن کے ذریعے ہوتی ہے۔ وزٹ ویزا کبھی ورک ویزا نہیں ہوتا۔"),
    ("cash_no_receipt", r"\bcash\b|naqd|نقد|no\s+receipt|without\s+receipt|personal\s+account|easypaisa|jazz\s*cash|رسید\s*نہیں",
     "Asks for cash, a personal account or mobile wallet, or no receipt. Real fees are paid to the embassy/VFS or against a "
     "proper company receipt.",
     "نقد رقم، ذاتی اکاؤنٹ یا موبائل والٹ میں ادائیگی، یا بغیر رسید کا مطالبہ۔ اصل فیس سفارت خانے/(VFS) کو یا باقاعدہ کمپنی رسید پر ادا ہوتی ہے۔"),
    ("urgency", r"limited\s+seats|today\s+only|last\s+chance|hurry|jaldi|فوری|آخری\s*موقع|only\s+\d+\s+seats",
     "Pressure tactics (limited seats, today only). Honest agencies don't rush you into paying.",
     "دباؤ کے حربے (محدود سیٹیں، صرف آج)۔ دیانت دار ایجنسیاں ادائیگی کے لیے جلدی نہیں کرواتیں۔"),
    ("fake_docs", r"dummy|arrange\s+(?:bank|statement|funds|balance)|statement\s+(?:bana|arrange)|fake|jaali|جعلی|backdated",
     "Offers to 'arrange' bank statements, dummy bookings or documents. Fake documents lead to refusal and can lead to a "
     "multi-year ban and criminal charges.",
     "بینک اسٹیٹمنٹ، ڈمی بکنگ یا دستاویزات 'بنانے' کی پیشکش۔ جعلی دستاویزات پر ویزا مسترد ہوتا ہے اور کئی سال کی پابندی اور فوجداری مقدمہ ہو سکتا ہے۔"),
    ("passport_hold", r"(?:submit|give|hand\s+over|deposit)\s+(?:your\s+)?(?:original\s+)?passport|passport\s+jama",
     "Wants to keep your original passport before anything is booked. Never hand over your passport without a written receipt "
     "and a real appointment.",
     "کسی بکنگ سے پہلے اصل پاسپورٹ رکھنا چاہتا ہے۔ تحریری رسید اور حقیقی اپائنٹمنٹ کے بغیر کبھی پاسپورٹ نہ دیں۔"),
    ("no_protector", r"no\s+protector|without\s+protector|protector\s+(?:nahi|not\s+needed)",
     "Says you don't need the Protector of Emigrants stamp. Anyone going abroad for work needs it.",
     "کہتا ہے کہ پروٹیکٹر کی ضرورت نہیں۔ کام کے لیے بیرونِ ملک جانے والے ہر شخص کے لیے یہ لازمی ہے۔"),
    ("free_visa", r"free\s+visa|visa\s+free\s+work|فری\s*ویزا",
     "'Free visa' offers for work abroad are a known trap — the worker usually ends up undocumented.",
     "بیرونِ ملک کام کے لیے 'فری ویزا' ایک معروف جال ہے — کارکن عموماً غیر قانونی رہ جاتا ہے۔"),
]

COUNTRY_WORDS = {
    "GB": r"\buk\b|united kingdom|britain|england|london|برطانیہ|لندن",
    "CA": r"canada|کینیڈا",
    "DE": r"germany|schengen|europe|جرمنی|یورپ",
    "TR": r"turkey|türkiye|turkiye|ترکی|ترکیہ",
    "AE": r"\buae\b|dubai|emirates|دبئی",
    "MY": r"malaysia|ملائیشیا",
    "SA": r"saudi|umrah|سعودی|عمرہ",
    "US": r"\busa\b|america|امریکہ",
}

_LAKH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(lakh|lac|لاکھ|crore|کروڑ)", re.IGNORECASE)
_PKR_RE = re.compile(r"(?:rs\.?|pkr|روپے)\s*([\d,]+)|([\d,]{5,})\s*(?:rs|pkr|روپے)", re.IGNORECASE)
_LICENCE_RE = re.compile(r"\b(\d{3,5}/[A-Z]{3})\b")


def amounts_pkr(text: str) -> list[int]:
    """PKR amounts mentioned (in rupees), incl. lakh/crore."""
    out: list[int] = []
    for m in _LAKH_RE.finditer(text):
        mult = 10_000_000 if m.group(2).lower() in ("crore", "کروڑ") else 100_000
        out.append(int(float(m.group(1)) * mult))
    for m in _PKR_RE.finditer(text):
        n = (m.group(1) or m.group(2) or "").replace(",", "")
        if n.isdigit():
            out.append(int(n))
    return out


def detect_countries(text: str) -> list[str]:
    return [c for c, rx in COUNTRY_WORDS.items() if re.search(rx, text, re.IGNORECASE)]


def check(text: str) -> dict[str, Any]:
    t = text or ""
    flags = []
    for code, rx, en, ur in FLAGS:
        m = re.search(rx, t, re.IGNORECASE)
        if m:
            flags.append({"code": code, "en": en, "ur": ur, "evidence": m.group(0)})
    countries = detect_countries(t)
    amounts = amounts_pkr(t)
    facts: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    amount_strings: list[str] = [format_money(a * 100, "PKR") for a in amounts]

    # official fee comparison for each mentioned destination we cover
    for c in countries:
        vt = VISA_TYPES.get(c)
        if not vt:
            continue
        pol = knowledge.get_policy(c, vt, ["gov_fee", "service_centre_fee"])
        if "gov_fee" in pol:
            f = pol["gov_fee"]
            fee_minor = int(f.value["amount_minor"])
            fact = {"en": f"Official {country_name(c)} visit visa fee: {f.value['text']}.",
                    "ur": f"{country_name(c, 'ur')} وزٹ ویزا کی سرکاری فیس: {f.value['text']}۔",
                    "citation": f.citation.model_dump(), "fresh": f.fresh}
            facts.append(fact)
            citations.append(f.citation.model_dump())
            amount_strings.append(f.value["text"])
            if amounts:
                try:
                    from .db import tx
                    with tx() as conn:
                        rates = {r["currency"]: str(r["rate_to_pkr"]) for r in conn.execute("select * from fx_rates")}
                    official_pkr = convert_minor(fee_minor, f.value["currency"], "PKR", rates) // 100
                except Exception:
                    official_pkr = 0
                biggest = max(amounts)
                amount_strings.append(format_money(official_pkr * 100, "PKR"))
                if official_pkr and biggest > official_pkr * 5:
                    flags.append({
                        "code": "overpriced",
                        "en": f"You were asked for about {format_money(biggest * 100, 'PKR')}, many times the official fee "
                              f"(about {format_money(official_pkr * 100, 'PKR')} at current rates). Even with genuine service "
                              "charges this gap is a warning sign.",
                        "ur": f"آپ سے تقریباً {format_money(biggest * 100, 'PKR')} مانگے گئے، جو سرکاری فیس "
                              f"(موجودہ ریٹ پر تقریباً {format_money(official_pkr * 100, 'PKR')}) سے کئی گنا زیادہ ہے۔",
                        "evidence": format_money(biggest * 100, "PKR"),
                    })
    work_related = any(f["code"] in ("work_visa", "free_visa", "no_protector") for f in flags)
    scam_hits = knowledge.search_snapshots("licensed promoters OEP" if work_related else "guarantee visa fraud complaint",
                                           country="PK", topic="scam_warning", limit=2)
    for h in scam_hits:
        facts.append({"en": h["excerpt"], "ur": h["excerpt"], "citation": h["citation"], "fresh": True, "excerpt": True})
        citations.append(h["citation"])

    licence = None
    m = _LICENCE_RE.search(t)
    if m:
        licence = {"number": m.group(1), **knowledge.verify_agent_licence(m.group(1))}
        if not licence["found"]:
            flags.append({"code": "licence_not_found",
                          "en": f"Licence {m.group(1)} was not found in our latest copy of the BEOE list. Verify it directly "
                                "with BEOE before paying anything.",
                          "ur": f"لائسنس {m.group(1)} ہماری (BEOE) فہرست کی تازہ کاپی میں نہیں ملا۔ کوئی ادائیگی سے پہلے براہِ راست (BEOE) سے تصدیق کریں۔",
                          "evidence": m.group(1)})
        elif str(licence.get("status", "")).lower() != "valid":
            flags.append({"code": "licence_not_valid",
                          "en": f"Licence {m.group(1)} is listed by BEOE as '{licence['status']}'.",
                          "ur": f"لائسنس {m.group(1)} کو (BEOE) نے '{licence['status']}' درج کیا ہے۔", "evidence": m.group(1)})

    severe = {"guarantee", "work_visa", "fake_docs", "free_visa", "licence_not_valid", "no_protector"}
    risk = "high" if any(f["code"] in severe for f in flags) or len(flags) >= 3 else ("medium" if flags else "low")
    steps = verification_steps(work_related)
    return {
        "type": "scam_check", "risk": risk, "red_flags": flags, "official_facts": facts, "countries": countries,
        "amounts_pkr": amounts, "amount_strings": amount_strings, "licence": licence, "verification_steps": steps,
        "citations": list({c["url"]: c for c in citations}.values()),
    }


def verification_steps(work_related: bool) -> list[dict[str, str]]:
    steps = [
        {"en": "Ask for the agency's registered company name, office address and licence number in writing.",
         "ur": "ایجنسی کا رجسٹرڈ نام، دفتر کا پتہ اور لائسنس نمبر تحریری طور پر مانگیں۔"},
        {"en": "Check official fees yourself on the embassy, VFS/TLS or e-visa website. Pay government fees only there.",
         "ur": "سرکاری فیس خود سفارت خانے، (VFS/TLS) یا (e-Visa) ویب سائٹ پر چیک کریں۔ سرکاری فیس صرف وہیں ادا کریں۔"},
        {"en": "Never pay cash without a printed receipt on company letterhead. Prefer bank transfer to a company account.",
         "ur": "کمپنی لیٹر ہیڈ پر چھپی رسید کے بغیر کبھی نقد ادائیگی نہ کریں۔ کمپنی اکاؤنٹ میں بینک ٹرانسفر بہتر ہے۔"},
        {"en": "Report fraud to the FIA through the complaint channels listed on fia.gov.pk.",
         "ur": "فراڈ کی شکایت (FIA) کو fia.gov.pk پر دیے گئے شکایتی ذرائع سے کریں۔"},
    ]
    if work_related:
        steps.insert(1, {"en": "For any job abroad: verify the promoter's OEP licence on the BEOE website or at the Protector of "
                               "Emigrants office, and get Protector registration before travelling.",
                         "ur": "بیرونِ ملک کسی بھی نوکری کے لیے: (BEOE) ویب سائٹ یا پروٹیکٹر آف ایمیگرنٹس دفتر سے پروموٹر کا (OEP) "
                               "لائسنس چیک کریں، اور سفر سے پہلے پروٹیکٹر رجسٹریشن کروائیں۔"})
    return steps
