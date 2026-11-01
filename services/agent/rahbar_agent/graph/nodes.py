"""Graph nodes. Each node does the factual work (tools) and writes a compliant bilingual draft;
`respond` phrases it (LLM if available), validates it, and streams it."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from .. import actions, cases, knowledge, pricing, scam, umrah
from ..assessment import Profile, Trip, assess, assessment_card
from ..compose import compose
from ..db import tx
from ..i18n import RATING_UR, VISA_TYPES, country_name
from ..money import format_money
from ..providers.flights import FlightSearch, get_flight_provider
from ..providers.hotels import HotelSearch, get_hotel_provider
from .router import parse_profile_text, route
from .state import AgentState

COVERED = set(VISA_TYPES)
REQUIREMENT_FIELDS = ["required_documents", "gov_fee", "service_centre_fee", "processing_time", "max_stay",
                      "biometrics_required", "proof_of_funds", "apply_from", "insurance_required"]


def _w() -> Any:
    try:
        return get_stream_writer()
    except Exception:  # outside a streaming run (e.g. unit tests calling nodes directly)
        return lambda _x: None


def progress(en: str, ur: str) -> None:
    _w()({"event": "progress", "data": {"step": en, "step_ur": ur}})


def L(state: AgentState, en: str, ur: str) -> str:
    return ur if state.locale == "ur" else en


def _last_user_text(state: AgentState) -> str:
    for m in reversed(state.messages):
        if m["role"] == "user":
            return m["content"]
    return ""


def _cites(facts: dict[str, knowledge.PolicyFact]) -> list[dict[str, Any]]:
    return list({f.citation.url: f.citation.model_dump() for f in facts.values()}.values())


def _fact_line(state: AgentState, f: knowledge.PolicyFact, label_en: str, label_ur: str) -> str:
    v = f.value
    if isinstance(v, dict):
        v = v.get("text") or v
    if isinstance(v, list):
        v = "; ".join(map(str, v))
    stale = "" if f.fresh else L(state, " (may be out of date — re-checking)", " (پرانی ہو سکتی ہے — دوبارہ چیک ہو رہی ہے)")
    return f"- {L(state, label_en, label_ur)}: {v}{stale}"


def _fixture_note(state: AgentState, cites: list[dict[str, Any]]) -> str:
    if any(c.get("is_test_fixture") for c in cites):
        return "\n\n" + L(state, "⚠️ Note: these sources are TEST DATA in this environment, not official information.",
                          "⚠️ نوٹ: اس ماحول میں یہ ذرائع ٹیسٹ ڈیٹا ہیں، سرکاری معلومات نہیں۔")
    return ""


DISCLAIMER = ("The decision is always the embassy's — no one can guarantee a visa.",
              "فیصلہ ہمیشہ سفارت خانے کا ہوتا ہے — کوئی بھی ویزا کی گارنٹی نہیں دے سکتا۔")


# ----------------------------------------------------------------------------------------------- router
def router_node(state: AgentState) -> dict[str, Any]:
    text = _last_user_text(state)
    progress("Understanding your request", "آپ کی بات سمجھ رہے ہیں")
    intent, slots = route(text, state.payload, state.messages)
    trip = {**state.trip, **{k: v for k, v in slots.items() if k in ("travellers", "days", "for_whom")}}
    return {
        "intent": intent, "destination": slots.get("destination") or state.destination,
        "visa_type": slots.get("visa_type") or state.visa_type, "trip": trip,
        "facts": {}, "citations": [], "cards": [], "allowed_amounts": [], "reply": None, "pending_action": None,
    }


# ----------------------------------------------------------------------------------------------- simple
def smalltalk_node(state: AgentState) -> dict[str, Any]:
    return {"reply": L(state,
        "Assalam-o-alaikum! I'm Rahbar. I can tell you honestly what a visa needs and costs (with official sources), "
        "assess your chances, check if an agent's offer is a scam, and plan Umrah, flights and hotels. "
        "Which country are you thinking of, and who is travelling?",
        "السلام علیکم! میں رہبر ہوں۔ میں آپ کو سرکاری ذرائع کے ساتھ ایمانداری سے بتا سکتا ہوں کہ ویزا کے لیے کیا چاہیے اور "
        "کتنا خرچ آتا ہے، آپ کے امکانات کا جائزہ لے سکتا ہوں، کسی ایجنٹ کی پیشکش فراڈ تو نہیں یہ چیک کر سکتا ہوں، اور عمرہ، "
        "فلائٹ اور ہوٹل کی منصوبہ بندی کر سکتا ہوں۔ آپ کس ملک جانا چاہتے ہیں اور کون سفر کر رہا ہے؟")}


def fraud_node(state: AgentState) -> dict[str, Any]:
    return {"reply": L(state,
        "I can't help with that. Fake or 'arranged' bank statements, dummy letters or sponsors are detected by embassies "
        "far more often than agents admit. The result is a refusal on your record, often a ban of several years, and in "
        "Pakistan it can mean an FIA case. What I can do is help you build a genuine file: what to show, how to explain your "
        "income honestly, and whether a sponsor or waiting a few months would make your application stronger.",
        "میں اس میں مدد نہیں کر سکتا۔ جعلی یا 'بنائے گئے' بینک اسٹیٹمنٹ، ڈمی خطوط یا اسپانسر سفارت خانے ایجنٹوں کے دعووں سے "
        "کہیں زیادہ پکڑ لیتے ہیں۔ نتیجہ: آپ کے ریکارڈ پر انکار، اکثر کئی سال کی پابندی، اور پاکستان میں (FIA) کا مقدمہ بھی ہو سکتا ہے۔ "
        "میں آپ کی اصل فائل مضبوط بنانے میں مدد کر سکتا ہوں: کیا دکھانا ہے، آمدنی کیسے ایمانداری سے واضح کرنی ہے، اور کیا اسپانسر "
        "یا چند ماہ انتظار درخواست کو مضبوط کرے گا۔")}


def work_visa_node(state: AgentState) -> dict[str, Any]:
    hits = knowledge.search_snapshots("licensed promoters OEP employment", country="PK", topic="scam_warning", limit=2)
    cites = [h["citation"] for h in hits]
    base = L(state,
        "We don't offer work visas or job placements. Legal overseas employment from Pakistan goes through Overseas "
        "Employment Promoters licensed by the Bureau of Emigration (BEOE), and you must register with the Protector of "
        "Emigrants before you travel. A visit visa is never a work visa — anyone selling one is breaking the law.\n\n"
        "To check an agent: ask for their OEP licence number and verify it with BEOE (or paste it here and I'll check our "
        "latest copy of the BEOE list).",
        "ہم ورک ویزا یا نوکری فراہم نہیں کرتے۔ پاکستان سے قانونی بیرونِ ملک ملازمت بیورو آف ایمیگریشن (BEOE) کے لائسنس یافتہ "
        "اوورسیز ایمپلائمنٹ پروموٹرز کے ذریعے ہوتی ہے، اور سفر سے پہلے پروٹیکٹر آف ایمیگرنٹس کے ہاں رجسٹریشن لازمی ہے۔ وزٹ ویزا "
        "کبھی ورک ویزا نہیں ہوتا — جو بیچ رہا ہے وہ قانون توڑ رہا ہے۔\n\nایجنٹ کو چیک کرنے کے لیے: ان سے (OEP) لائسنس نمبر "
        "مانگیں اور (BEOE) سے تصدیق کریں (یا یہاں لکھیں، میں (BEOE) فہرست کی تازہ کاپی میں دیکھ لوں گا)۔")
    return {"reply": base + _fixture_note(state, cites), "citations": cites}


# ----------------------------------------------------------------------------------------------- knowledge
def quick_answer_node(state: AgentState) -> dict[str, Any]:
    d = state.destination
    if not d:
        return {"reply": L(state, "Which country is the trip to? I currently cover the UK, Schengen (Germany), Türkiye, "
                           "UAE, Malaysia and Saudi Arabia (tourist and Umrah).",
                           "سفر کس ملک کا ہے؟ ابھی میں برطانیہ، (Schengen) جرمنی، ترکیہ، یو اے ای، ملائیشیا اور سعودی عرب "
                           "(سیاحتی اور عمرہ) کی معلومات دیتا ہوں۔")}
    if d not in COVERED:
        return {"reply": L(state,
            f"I don't cover {country_name(d)} yet, so I can't give you verified requirements or fees for it. Please check the "
            "official embassy website directly, and be careful with agents who claim inside knowledge.",
            f"میں ابھی {country_name(d, 'ur')} کی معلومات نہیں دیتا، اس لیے تصدیق شدہ ضروریات یا فیس نہیں بتا سکتا۔ براہِ کرم "
            "سفارت خانے کی سرکاری ویب سائٹ دیکھیں، اور 'اندر کی معلومات' کا دعویٰ کرنے والے ایجنٹوں سے محتاط رہیں۔")}
    vt = state.visa_type or VISA_TYPES[d]
    progress(f"Checking official {country_name(d)} requirements", f"{country_name(d, 'ur')} کی سرکاری شرائط چیک کر رہے ہیں")
    facts, unverified = knowledge.ensure_fresh_policy(
        d, vt, REQUIREMENT_FIELDS,
        progress=lambda _k, title: progress(f"Re-checking {title}", f"{title} دوبارہ چیک کر رہے ہیں"))
    progress("Preparing an honest answer", "ایماندار جواب تیار کر رہے ہیں")
    if not facts:
        return {"reply": L(state,
            f"I couldn't verify the current {country_name(d)} requirements from official sources right now, so I won't guess. "
            "Please try again shortly.",
            f"میں ابھی سرکاری ذرائع سے {country_name(d, 'ur')} کی موجودہ شرائط کی تصدیق نہیں کر سکا، اس لیے اندازہ نہیں لگاؤں گا۔ "
            "تھوڑی دیر بعد دوبارہ کوشش کریں۔")}
    who = state.trip.get("for_whom") == "parents"
    lines = [L(state, f"Here is what {country_name(d)} officially asks for" + (" (each parent applies separately)" if who else "") + ":",
               f"{country_name(d, 'ur')} سرکاری طور پر یہ مانگتا ہے" + (" (والدین میں سے ہر ایک کی الگ درخواست)" if who else "") + ":")]
    labels = {
        "gov_fee": ("Government visa fee", "حکومتی ویزا فیس"), "service_centre_fee": ("Application centre fee", "درخواست مرکز (VFS) فیس"),
        "processing_time": ("Usual processing time", "عام پراسیسنگ وقت"), "max_stay": ("Maximum stay", "زیادہ سے زیادہ قیام"),
        "biometrics_required": ("Biometrics", "(Biometrics)"), "apply_from": ("Where to apply", "کہاں اپلائی کریں"),
        "proof_of_funds": ("Proof of funds", "مالی ثبوت (Proof of funds)"), "insurance_required": ("Travel insurance", "سفری انشورنس"),
    }
    for field, (en, ur) in labels.items():
        if field in facts:
            lines.append(_fact_line(state, facts[field], en, ur))
    checklist = None
    if "required_documents" in facts:
        docs = facts["required_documents"]
        lines.append(L(state, "\nDocuments (full checklist below):", "\nدستاویزات (مکمل فہرست نیچے):"))
        checklist = {"type": "checklist", "title_en": f"{country_name(d)} visit visa documents",
                     "title_ur": f"{country_name(d, 'ur')} وزٹ ویزا دستاویزات", "items": docs.value,
                     "citation": docs.citation.model_dump(), "fresh": docs.fresh}
    if who:
        lines.append(L(state, "\nFor parents: if you are paying, add your own bank statements, proof of income and a letter "
                       "explaining the visit. Their own ties to Pakistan (home, family, pension) matter a lot.",
                       "\nوالدین کے لیے: اگر آپ خرچ اٹھا رہے ہیں تو اپنے بینک اسٹیٹمنٹ، آمدنی کا ثبوت اور وزٹ کی وضاحت کا خط شامل کریں۔ "
                       "ان کے اپنے پاکستان سے تعلقات (گھر، خاندان، پنشن) بہت اہم ہیں۔"))
    if unverified:
        lines.append(L(state, "\nSome items could not be re-verified just now and are marked as possibly out of date.",
                       "\nکچھ معلومات ابھی دوبارہ تصدیق نہیں ہو سکیں اور ممکنہ طور پر پرانی کے طور پر نشان زد ہیں۔"))
    lines.append("\n" + L(state, "Sources and their last-verified dates are shown below. " + DISCLAIMER[0] +
                          " If you like, tell me about the traveller(s) and I'll give you an honest assessment of their chances.",
                          "ذرائع اور آخری تصدیق کی تاریخیں نیچے دی گئی ہیں۔ " + DISCLAIMER[1] +
                          " اگر چاہیں تو مسافر(وں) کے بارے میں بتائیں، میں ان کے امکانات کا ایماندار جائزہ دوں گا۔"))
    cites = _cites(facts)
    amounts = [f.value["text"] for k, f in facts.items() if k in ("gov_fee", "service_centre_fee") and f.value]
    cards = [checklist] if checklist else []
    cards.append(profile_form_card(state))
    return {"reply": "\n".join(lines) + _fixture_note(state, cites), "citations": cites, "cards": cards,
            "allowed_amounts": amounts, "facts": {k: v.model_dump() for k, v in facts.items()}}


def profile_form_card(state: AgentState) -> dict[str, Any]:
    return {"type": "profile_form", "destination": state.destination, "travellers": state.trip.get("travellers", 1),
            "days": state.trip.get("days", 14)}


def consult_node(state: AgentState) -> dict[str, Any]:
    return {"reply": L(state,
        "To give you an honest picture I need a few details: where you want to go, the purpose and rough dates, who is "
        "travelling, and for each traveller their work/income, savings, previous travel and any past refusals. You can "
        "fill in the short form below.",
        "ایماندار جائزے کے لیے مجھے چند تفصیلات چاہییں: کہاں جانا ہے، مقصد اور اندازاً تاریخیں، کون سفر کر رہا ہے، اور ہر مسافر "
        "کی ملازمت/آمدنی، بچت، پچھلا سفر اور اگر کبھی ویزا مسترد ہوا ہو۔ نیچے مختصر فارم بھر دیں۔"),
        "cards": [profile_form_card(state)]}


# ----------------------------------------------------------------------------------------------- assessment
def assess_node(state: AgentState) -> dict[str, Any]:
    text = _last_user_text(state)
    d = state.payload.get("destination") or state.destination
    raw = state.payload.get("profile") or {**(state.traveller_profiles[0] if state.traveller_profiles else {}),
                                            **parse_profile_text(text)}
    if not d or not raw.get("employment_status") and raw.get("funds_available_minor") is None:
        return consult_node(state)
    if d not in COVERED:
        return quick_answer_node(state.model_copy(update={"destination": d}))
    profile = Profile.model_validate(raw)
    trip = Trip(destination=d, purpose=state.payload.get("purpose", "tourism"),
                days=int(state.payload.get("days") or state.trip.get("days") or 14),
                travellers=int(state.payload.get("travellers") or state.trip.get("travellers") or 1))
    progress("Checking official requirements", "سرکاری شرائط چیک کر رہے ہیں")
    facts, _ = knowledge.ensure_fresh_policy(d, VISA_TYPES[d], REQUIREMENT_FIELDS)
    progress("Weighing strengths and weaknesses of the profile", "پروفائل کی مضبوطیوں اور کمزوریوں کا جائزہ")
    a = assess(profile, trip, facts)
    progress("Writing an honest assessment", "ایماندار جائزہ لکھ رہے ہیں")
    if state.case_id and state.user_id:
        from ..db import Jsonb
        with tx() as conn:
            conn.execute("update cases set strength_rating=%s, assessment=%s where id=%s and owner_id=%s",
                         (a.rating, Jsonb(a.model_dump()), state.case_id, state.user_id))
            cur = conn.execute("select status from cases where id=%s", (state.case_id,)).fetchone()
            if cur and cur["status"] in ("consulting", "assessed"):
                cases.transition(conn, state.case_id, "assessed", actor_type="ai", event="assessed", rating=a.rating)
    rating_en = a.rating.capitalize()
    lines = [L(state, f"My honest assessment for {country_name(d)}: **{rating_en}**.",
               f"{country_name(d, 'ur')} کے لیے میرا ایماندار جائزہ: **{RATING_UR[a.rating]}**۔")]
    for f in a.blockers:
        lines.append("⛔ " + L(state, f.en, f.ur))
    neg = [f for f in a.factors if f.impact == "negative"]
    pos = [f for f in a.factors if f.impact == "positive"]
    if neg:
        lines.append(L(state, "\nWeaknesses (please read these):", "\nکمزوریاں (براہِ کرم پڑھیں):"))
        lines += [f"- {L(state, f.en, f.ur)}" for f in neg]
    if pos:
        lines.append(L(state, "\nStrengths:", "\nمضبوط پہلو:"))
        lines += [f"- {L(state, f.en, f.ur)}" for f in pos]
    if a.improvements:
        lines.append(L(state, "\nWhat would make it stronger:", "\nکیا چیز اسے مضبوط بنائے گی:"))
        lines += [f"- {L(state, i['en'], i['ur'])}" for i in a.improvements]
    if a.missing_info:
        lines.append(L(state, "\nI'm missing some information, so treat this as provisional.",
                       "\nکچھ معلومات نہیں ملیں، اس لیے اسے عارضی سمجھیں۔"))
    if a.timeline:
        tl = a.timeline["processing_time"]
        lines.append(L(state, f"\nUsual processing time: {tl.get('text', tl)}.", f"\nعام پراسیسنگ وقت: {tl.get('text', tl)}۔"))
    lines.append(L(state, "\nThis rating is our own judgement of how strong the file is, not an official rule. " + DISCLAIMER[0],
                   "\nیہ درجہ بندی فائل کی مضبوطی کے بارے میں ہماری اپنی رائے ہے، سرکاری اصول نہیں۔ " + DISCLAIMER[1]))
    cites = a.citations
    amounts = [r["value"]["text"] for r in a.requirements if r["field"] == "gov_fee" and isinstance(r["value"], dict)]
    return {"reply": "\n".join(lines) + _fixture_note(state, cites), "citations": cites, "allowed_amounts": amounts,
            "cards": [assessment_card(a, state.case_id)], "destination": d,
            "facts": {"assessment": a.model_dump()}}


# ----------------------------------------------------------------------------------------------- quotes
def _need_login(state: AgentState) -> dict[str, Any]:
    return {"reply": L(state, "Please sign in first so I can open a case for you — every step, fee and reference number will "
                       "then be visible in your case timeline.",
                       "براہِ کرم پہلے سائن اِن کریں تاکہ میں آپ کا کیس کھول سکوں — پھر ہر قدم، فیس اور حوالہ نمبر آپ کے کیس "
                       "ٹائم لائن میں نظر آئے گا۔"), "cards": [{"type": "login_required"}]}


def build_quote_node(state: AgentState) -> dict[str, Any]:
    if not state.user_id:
        return _need_login(state)
    d = state.payload.get("destination") or state.destination
    if not d or d not in COVERED:
        return quick_answer_node(state)
    travellers = int(state.payload.get("travellers") or state.trip.get("travellers") or 1)
    progress("Checking current official fees", "موجودہ سرکاری فیس چیک کر رہے ہیں")
    facts, _ = knowledge.ensure_fresh_policy(d, VISA_TYPES[d], ["gov_fee", "service_centre_fee"])
    items = pricing.items_from_policy(facts, travellers, country_name(d))
    progress("Building an itemised quote", "تفصیلی قیمت نامہ بنا رہے ہیں")
    with tx() as conn:
        case_id = state.case_id
        if not case_id:
            case = cases.create_case(conn, state.user_id, "visit_visa", destination=d, purpose="tourism",
                                     trip={**state.trip, "travellers": travellers})
            case_id = str(case["id"])
        q = pricing.build_quote(conn, case_id, items, travellers=travellers)
    card = pricing.quote_card(q)
    lines = [L(state, "Here is your itemised quote. Every line shows who receives the money; our service fee is a separate line.",
               "یہ آپ کا تفصیلی قیمت نامہ ہے۔ ہر لائن میں لکھا ہے کہ رقم کس کو جاتی ہے؛ ہماری سروس فیس الگ لائن میں ہے۔"),
             L(state, f"Total: {format_money(card['total_minor'], 'PKR')}.", f"کل: {format_money(card['total_minor'], 'PKR')}۔")]
    if not card["binding"]:
        lines.append(L(state, "Some prices could not be confirmed from fresh official data, so this quote is indicative only "
                       "and can't be paid until we re-verify them.",
                       "کچھ قیمتوں کی تازہ سرکاری ڈیٹا سے تصدیق نہیں ہو سکی، اس لیے یہ قیمت نامہ صرف اندازہ ہے اور دوبارہ تصدیق تک "
                       "ادائیگی نہیں ہو سکتی۔"))
    lines.append(L(state, "Paying for the service does not change the embassy's decision. " + DISCLAIMER[0],
                   "سروس کی ادائیگی سفارت خانے کے فیصلے کو تبدیل نہیں کرتی۔ " + DISCLAIMER[1]))
    cites = _cites(facts)
    return {"reply": "\n".join(lines) + _fixture_note(state, cites), "cards": [card], "citations": cites,
            "allowed_amounts": pricing.quote_amount_strings(card), "case_id": case_id, "service_type": "visit_visa"}


# ----------------------------------------------------------------------------------------------- scam
def scam_node(state: AgentState) -> dict[str, Any]:
    text = state.payload.get("scam_text") or _last_user_text(state)
    progress("Looking for red flags", "خطرے کی علامات تلاش کر رہے ہیں")
    progress("Comparing with official fees and BEOE/FIA notices", "سرکاری فیس اور (BEOE/FIA) نوٹسز سے موازنہ")
    r = scam.check(text)
    risk = {"high": ("HIGH", "زیادہ"), "medium": ("MEDIUM", "درمیانہ"), "low": ("LOW", "کم")}[r["risk"]]
    lines = [L(state, f"Scam risk: **{risk[0]}**.", f"فراڈ کا خطرہ: **{risk[1]}**۔")]
    if r["red_flags"]:
        lines.append(L(state, "Red flags I found:", "مجھے یہ خطرے کی علامات ملیں:"))
        lines += [f"- {L(state, f['en'], f['ur'])}" for f in r["red_flags"]]
    else:
        lines.append(L(state, "I didn't find obvious red flags in this text, but please still verify the agent before paying.",
                       "اس متن میں واضح خطرے کی علامات نہیں ملیں، پھر بھی ادائیگی سے پہلے ایجنٹ کی تصدیق ضرور کریں۔"))
    fee_facts = [f for f in r["official_facts"] if not f.get("excerpt")]
    if fee_facts:
        lines.append(L(state, "\nOfficial facts (with sources below):", "\nسرکاری حقائق (ذرائع نیچے):"))
        lines += [f"- {L(state, f['en'], f['ur'])}" for f in fee_facts]
    lines.append(L(state, "\nHow to protect yourself:", "\nاپنی حفاظت کیسے کریں:"))
    lines += [f"- {L(state, s['en'], s['ur'])}" for s in r["verification_steps"]]
    lines.append(L(state, "\nIf you want to do this properly, I can show you the real requirements and costs and handle the "
                   "application with every step visible to you.",
                   "\nاگر آپ یہ کام درست طریقے سے کرنا چاہتے ہیں تو میں آپ کو اصل شرائط اور اخراجات دکھا سکتا ہوں اور درخواست کا "
                   "سارا کام کر سکتا ہوں، ہر قدم آپ کے سامنے۔"))
    amounts = r["amount_strings"]
    return {"reply": "\n".join(lines) + _fixture_note(state, r["citations"]), "cards": [r], "citations": r["citations"],
            "allowed_amounts": amounts, "facts": {"scam_check": r}}


# ----------------------------------------------------------------------------------------------- umrah
def umrah_node(state: AgentState) -> dict[str, Any]:
    p = state.payload
    if p.get("action") == "select_umrah_option":
        if not state.user_id:
            return _need_login(state)
        progress("Building your itemised Umrah quote", "آپ کا تفصیلی عمرہ قیمت نامہ بنا رہے ہیں")
        opt = p["option"]
        with tx() as conn:
            case = cases.create_case(conn, state.user_id, "umrah_package", destination="SA", purpose="umrah",
                                     trip={"travellers": opt["travellers"], "nights_makkah": opt["nights_makkah"],
                                           "nights_madinah": opt["nights_madinah"], "start": opt["start"]})
            conn.execute("update cases set partner_id=%s where id=%s", (opt["partner_id"], case["id"]))
            q = pricing.build_quote(conn, str(case["id"]), umrah.option_quote_items(opt), travellers=opt["travellers"])
        card = pricing.quote_card(q)
        return {"reply": L(state, "Here is the itemised quote for the package you chose. Hotels, flights and visa are booked "
                           "through our licensed Umrah partner; each line shows who is paid.",
                           "آپ کے منتخب کردہ پیکج کا تفصیلی قیمت نامہ یہ ہے۔ ہوٹل، فلائٹ اور ویزا ہمارے لائسنس یافتہ عمرہ پارٹنر کے "
                           "ذریعے بک ہوتے ہیں؛ ہر لائن میں لکھا ہے کہ رقم کس کو جاتی ہے۔"),
                "cards": [card], "allowed_amounts": pricing.quote_amount_strings(card), "case_id": str(case["id"]),
                "service_type": "umrah_package", "citations": [opt["citation"]] if opt.get("citation") else []}
    travellers = int(p.get("travellers") or state.trip.get("travellers") or 0)
    if not travellers or not p.get("start"):
        return {"reply": L(state,
            "Let's plan your Umrah. Tell me how many people are travelling, the dates, your departure city, how many nights "
            "in Makkah and Madinah, and how close to the Haram you'd like to stay. Use the form below.",
            "آئیے آپ کے عمرہ کی منصوبہ بندی کریں۔ بتائیں کتنے افراد سفر کر رہے ہیں، تاریخیں، روانگی کا شہر، مکہ اور مدینہ میں "
            "کتنی راتیں، اور حرم سے کتنا قریب رہنا چاہتے ہیں۔ نیچے فارم استعمال کریں۔"),
            "cards": [{"type": "umrah_form", "travellers": travellers or 2}]}
    progress("Checking partner inventory for your dates", "آپ کی تاریخوں کے لیے پارٹنر کی دستیابی چیک کر رہے ہیں")
    start = date.fromisoformat(p["start"])
    nm, nd = int(p.get("nights_makkah", 7)), int(p.get("nights_madinah", 5))
    options = umrah.build_options(start, nm, nd, travellers, p.get("origin", "LHE"))
    progress("Comparing package options", "پیکج کے اختیارات کا موازنہ")
    if not options:
        return {"reply": L(state, "I couldn't find partner inventory for those dates. Our team will check with the partner and "
                           "get back to you.", "ان تاریخوں کے لیے پارٹنر کی دستیابی نہیں ملی۔ ہماری ٹیم پارٹنر سے معلوم کر کے آپ کو بتائے گی۔")}
    card = {"type": "umrah_options", "options": options}
    amounts = [format_money(o["total_minor"], "PKR") for o in options]
    amounts += [format_money(li["amount_minor"], li["currency"]) for o in options for li in o["lines"]]
    lines = [L(state, f"I found {len(options)} options from our licensed partner. Each line shows the provider and price; "
               "hotel distances to the Haram are as provided by the partner.",
               f"ہمارے لائسنس یافتہ پارٹنر سے {len(options)} اختیارات ملے۔ ہر لائن میں فراہم کنندہ اور قیمت درج ہے؛ حرم سے ہوٹل "
               "کا فاصلہ پارٹنر کے مطابق ہے۔")]
    for o in options:
        lines.append(f"- {L(state, o['label_en'], o['label_ur'])}: {format_money(o['total_minor'], 'PKR')}")
    lines.append(L(state, "Prices are for the whole group and exclude our service fee, which is added as its own line when you "
                   "choose an option.", "قیمتیں پورے گروپ کے لیے ہیں اور ہماری سروس فیس شامل نہیں، جو اختیار منتخب کرنے پر الگ لائن میں شامل ہوگی۔"))
    cites = list({o["citation"]["url"]: o["citation"] for o in options}.values())
    return {"reply": "\n".join(lines) + _fixture_note(state, cites), "cards": [card], "allowed_amounts": amounts,
            "citations": cites}


def _offer_citation(provider: str, kind: str) -> dict[str, Any]:
    from datetime import UTC, datetime

    return {"url": f"provider:{provider}:{kind}", "title": f"Live {kind} offer ({provider})", "authority": provider,
            "verified_at": datetime.now(UTC).isoformat(), "is_test_fixture": provider == "sandbox"}


# ----------------------------------------------------------------------------------------------- flights/hotels
def booking_node(state: AgentState) -> dict[str, Any]:
    p = state.payload
    if p.get("action") == "search_flights":
        progress("Searching flights", "فلائٹس تلاش کر رہے ہیں")
        req = FlightSearch(origin=p["origin"], destination=p["destination"], depart_date=date.fromisoformat(p["depart_date"]),
                           return_date=date.fromisoformat(p["return_date"]) if p.get("return_date") else None,
                           adults=int(p.get("adults", 1)))
        offers = get_flight_provider().search(req)
        card = {"type": "flight_options", "search": req.model_dump(mode="json"),
                "offers": [o.model_dump(mode="json") for o in offers]}
        amounts = [format_money(o.fare_minor + o.taxes_minor, o.currency) for o in offers]
        return {"reply": L(state, f"I found {len(offers)} options. Fare, taxes and our service fee are shown separately when you "
                           "pick one. Check the baggage and refund rules on each option.",
                           f"{len(offers)} اختیارات ملے۔ کوئی منتخب کرنے پر کرایہ، ٹیکس اور ہماری سروس فیس الگ الگ دکھائے جائیں گے۔ "
                           "ہر اختیار کے سامان اور واپسی کے قوانین ضرور دیکھیں۔")
                + ("\n\n" + L(state, "⚠️ These are SANDBOX fares for testing, not real prices.",
                              "⚠️ یہ ٹیسٹنگ کے لیے (SANDBOX) کرائے ہیں، اصل قیمتیں نہیں۔") if offers and offers[0].provider == "sandbox" else ""),
                "cards": [card], "allowed_amounts": amounts, "citations": [_offer_citation(get_flight_provider().name, "flight")]}
    if p.get("action") == "search_hotels":
        progress("Searching hotels", "ہوٹل تلاش کر رہے ہیں")
        req_h = HotelSearch(city=p["city"], check_in=date.fromisoformat(p["check_in"]),
                            check_out=date.fromisoformat(p["check_out"]), guests=int(p.get("guests", 2)))
        offers_h = get_hotel_provider().search(req_h)
        card = {"type": "hotel_options", "search": req_h.model_dump(mode="json"),
                "offers": [o.model_dump(mode="json") for o in offers_h]}
        return {"reply": L(state, "Here are hotel options. The cancellation policy is shown on each one — please read it before "
                           "you confirm.", "یہ ہوٹل کے اختیارات ہیں۔ ہر ایک پر منسوخی کی پالیسی درج ہے — تصدیق سے پہلے ضرور پڑھیں۔")
                + ("\n\n" + L(state, "⚠️ SANDBOX prices for testing.", "⚠️ ٹیسٹنگ کے لیے (SANDBOX) قیمتیں۔")),
                "cards": [card], "allowed_amounts": [format_money(o.total_minor, o.currency) for o in offers_h],
                "citations": [_offer_citation(get_hotel_provider().name, "hotel")]}
    if p.get("action") == "select_offer":
        if not state.user_id:
            return _need_login(state)
        offer = p["offer"]
        kind = p.get("kind", "flight")
        progress("Building an itemised quote", "تفصیلی قیمت نامہ بنا رہے ہیں")
        with tx() as conn:
            case = cases.create_case(conn, state.user_id, kind, destination=offer.get("destination") or offer.get("city"),
                                     trip={"offer": offer})
            items = umrah.offer_quote_items(kind, offer)
            q = pricing.build_quote(conn, str(case["id"]), items, travellers=1,
                                    valid_until=date_to_dt(offer.get("expires_at")))
        card = pricing.quote_card(q)
        return {"reply": L(state, "Here is the itemised price for this option. Nothing is booked until you accept, pay, and confirm.",
                           "اس اختیار کی تفصیلی قیمت یہ ہے۔ جب تک آپ قبول، ادائیگی اور تصدیق نہ کریں، کچھ بک نہیں ہوگا۔"),
                "cards": [card], "allowed_amounts": pricing.quote_amount_strings(card), "case_id": str(case["id"]),
                "service_type": kind, "citations": [_offer_citation(offer.get("provider", "sandbox"), kind)]}
    return {"reply": L(state, "I can search flights and hotels for you. Use the search form below.",
                       "میں آپ کے لیے فلائٹس اور ہوٹل تلاش کر سکتا ہوں۔ نیچے سرچ فارم استعمال کریں۔"),
            "cards": [{"type": "booking_form", "today": (date.today() + timedelta(days=14)).isoformat()}]}


def date_to_dt(s: str | None) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(s) if s else None


def refusal_node(state: AgentState) -> dict[str, Any]:
    return {"reply": L(state,
        "I'm sorry about the refusal. Refusal letters list specific reasons — usually doubts about funds, ties to Pakistan, the "
        "purpose of the trip, or inconsistent documents. If you share the refusal letter in your case, I'll go through each "
        "reason honestly and tell you whether reapplying makes sense now, what must change first, or whether it's better to "
        "wait. Reapplying with the same file usually leads to the same result.",
        "ویزا مسترد ہونے پر افسوس ہے۔ انکار کے خط میں مخصوص وجوہات درج ہوتی ہیں — عموماً رقم، پاکستان سے تعلق، سفر کے مقصد یا "
        "دستاویزات میں تضاد پر شکوک۔ اگر آپ اپنے کیس میں انکار کا خط شیئر کریں تو میں ہر وجہ کا ایمانداری سے جائزہ لے کر بتاؤں گا "
        "کہ ابھی دوبارہ اپلائی کرنا مناسب ہے یا پہلے کیا بدلنا ضروری ہے، یا انتظار بہتر ہے۔ اسی فائل سے دوبارہ اپلائی کا نتیجہ "
        "عموماً وہی رہتا ہے۔")}


# ----------------------------------------------------------------------------------------------- confirmation
def confirm_node(state: AgentState) -> dict[str, Any]:
    """LangGraph interrupt for explicit user confirmation of an irreversible step."""
    pa = state.pending_action
    if not pa:
        return {}
    answer = interrupt({"card": pa})
    if not isinstance(answer, dict) or not answer.get("confirmed"):
        return {"reply": L(state, "Okay — nothing has been submitted. You can review and confirm whenever you're ready.",
                           "ٹھیک ہے — کچھ جمع نہیں ہوا۔ جب تیار ہوں، جائزہ لے کر تصدیق کر دیں۔"), "pending_action": None}
    with tx() as conn:
        a = actions.confirm_by_user(conn, pa["action_id"], state.user_id or "", answer.get("declarations"))
    return {"reply": L(state, "Thank you, confirmed. Our team will now review and carry out this step, and you'll see the real "
                       "reference number in your case timeline.",
                       "شکریہ، تصدیق ہو گئی۔ اب ہماری ٹیم اس قدم کا جائزہ لے کر اسے مکمل کرے گی، اور آپ کو کیس ٹائم لائن میں اصل حوالہ "
                       "نمبر نظر آئے گا۔"), "pending_action": actions.confirm_card(a), "cards": [actions.confirm_card(a)]}


def submit_pack_node(state: AgentState) -> dict[str, Any]:
    """User asks to submit a ready pack from chat -> pending action -> confirm interrupt."""
    if not state.user_id or not state.case_id:
        return _need_login(state)
    from ..packs import request_submission

    with tx() as conn:
        a = request_submission(conn, state.case_id, state.user_id)
    card = actions.confirm_card(a)
    return {"pending_action": card, "cards": [card]}


# ----------------------------------------------------------------------------------------------- respond
def respond_node(state: AgentState) -> dict[str, Any]:
    draft = state.reply or ""
    text, method = compose(locale=state.locale, intent=state.intent or "unknown", user_text=_last_user_text(state),
                           history=state.messages, facts=state.facts, citations=state.citations,
                           allowed_amounts=state.allowed_amounts, template=draft,
                           tier="deep" if state.intent in ("assess_eligibility", "plan_umrah", "refusal_analysis") else "standard")
    w = _w()
    for c in state.citations:
        w({"event": "citation", "data": c})
    words = re.split(r"(\s+)", text)
    for i in range(0, len(words), 6):
        w({"event": "token", "data": {"text": "".join(words[i:i + 6])}})
    for card in state.cards:
        w({"event": "card", "data": card})
    return {"messages": [{"role": "assistant", "content": text, "cards": state.cards, "citations": state.citations,
                          "method": method}], "reply": text}
