"""Honest eligibility assessment (PRD J1 step 2, CLAUDE.md rule 4).

The rating is computed from explicit, explainable factors so it is consistent and testable.
These factors are Rahbar's own judgement of application strength, not official rules — the UI
labels them that way. Official requirements come from cited policy records.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .knowledge import PolicyFact

Rating = Literal["strong", "fair", "weak"]
STRONG_TRAVEL = {"GB", "US", "CA", "AU", "NZ", "IE", "JP"} | {
    "DE", "FR", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "NO", "DK", "FI", "PT", "GR", "PL", "CZ", "HU"}
SCHENGEN = {"DE", "FR", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "NO", "DK", "FI", "PT", "GR", "PL", "CZ", "HU"}

# indicative funds a careful applicant should be able to show per day of stay (PKR), our heuristic
FUNDS_PER_DAY_PKR = {"GB": 30_000, "DE": 15_000, "TR": 14_000, "AE": 10_000, "MY": 8_000, "SA": 12_000}


class Profile(BaseModel):
    employment_status: Literal["employed", "self_employed", "business_owner", "student", "retired",
                               "homemaker", "unemployed"] | None = None
    employer: str | None = None
    monthly_income_minor: int | None = Field(default=None, ge=0)      # PKR minor units
    funds_available_minor: int | None = Field(default=None, ge=0)     # PKR minor units
    travel_history: list[dict[str, Any]] = []      # [{country, year, visa_type}]
    prior_refusals: list[dict[str, Any]] = []      # [{country, year, reason}]
    sponsor: dict[str, Any] | None = None          # {relationship, country, covers_costs}
    ties_to_pakistan: dict[str, Any] | None = None # {family, property, job}
    age: int | None = None


class Trip(BaseModel):
    destination: str
    purpose: str = "tourism"
    days: int = Field(default=14, ge=1, le=365)
    travellers: int = Field(default=1, ge=1, le=20)


class Factor(BaseModel):
    code: str
    impact: Literal["positive", "negative", "blocker"]
    weight: int
    en: str
    ur: str


class Assessment(BaseModel):
    rating: Rating
    score: int
    factors: list[Factor]
    improvements: list[dict[str, str]]
    blockers: list[Factor]
    requirements: list[dict[str, Any]]   # cited official facts
    timeline: dict[str, Any] | None
    missing_info: list[str]
    citations: list[dict[str, Any]]


def _f(code: str, impact: str, weight: int, en: str, ur: str) -> Factor:
    return Factor(code=code, impact=impact, weight=weight, en=en, ur=ur)  # type: ignore[arg-type]


def assess(profile: Profile, trip: Trip, facts: dict[str, PolicyFact]) -> Assessment:
    d = trip.destination
    factors: list[Factor] = []
    improvements: list[dict[str, str]] = []
    missing: list[str] = []
    visited = {str(t.get("country", "")).upper() for t in profile.travel_history}
    strong_visas = visited & STRONG_TRAVEL

    # --- destination-specific eligibility rules (from cited official pages, see fixtures/sources)
    if d == "TR" and not strong_visas:
        factors.append(_f("tr_evisa_condition", "blocker", -5,
            "Türkiye's e-Visa for Pakistani citizens needs a valid UK, US, Schengen or Irish visa or residence permit. "
            "Without one you must apply for a sticker visa through the embassy/application centre instead.",
            "پاکستانی شہریوں کے لیے ترکیہ کا (e-Visa) صرف اس صورت میں ہے جب آپ کے پاس برطانیہ، امریکہ، (Schengen) یا آئرلینڈ "
            "کا درست ویزا یا رہائشی اجازت نامہ ہو۔ اس کے بغیر سفارت خانے کے ذریعے عام ویزا لینا ہوگا۔"))
    if d == "SA" and trip.purpose != "umrah" and not (strong_visas & ({"US", "GB"} | SCHENGEN)):
        factors.append(_f("sa_evisa_condition", "blocker", -5,
            "Saudi Arabia's tourist eVisa for Pakistani citizens requires a US, UK or Schengen visa that has been used.",
            "پاکستانی شہریوں کے لیے سعودی (eVisa) کے لیے استعمال شدہ امریکی، برطانوی یا (Schengen) ویزا ضروری ہے۔"))

    # --- employment / income
    es = profile.employment_status
    if es is None:
        missing.append("employment_status")
    elif es in ("employed", "self_employed", "business_owner"):
        factors.append(_f("employment", "positive", 2, "Stable employment or business is a strong tie to Pakistan.",
                          "مستحکم ملازمت یا کاروبار پاکستان سے مضبوط تعلق ظاہر کرتا ہے۔"))
    elif es == "retired":
        factors.append(_f("retired", "positive", 1, "Retired with pension/family ties — show pension and property records.",
                          "ریٹائرڈ — پنشن اور جائیداد کے ثبوت دکھائیں۔"))
    elif es == "unemployed":
        factors.append(_f("unemployed", "negative", -2,
            "No current employment: embassies may doubt that you will return. This is a real weakness.",
            "موجودہ ملازمت نہیں: سفارت خانہ واپسی پر شک کر سکتا ہے۔ یہ ایک حقیقی کمزوری ہے۔"))
        improvements.append({"en": "Show other strong ties: property, family responsibilities, a sponsor's documents.",
                             "ur": "دوسرے مضبوط تعلقات دکھائیں: جائیداد، خاندانی ذمہ داریاں، اسپانسر کی دستاویزات۔"})
    elif es in ("student", "homemaker"):
        if not profile.sponsor:
            factors.append(_f("dependent_no_sponsor", "negative", -1,
                "As a student/homemaker you will need a sponsor (usually a parent or spouse) and their documents.",
                "طالب علم/گھریلو خاتون کے طور پر آپ کو اسپانسر (عموماً والدین یا شریکِ حیات) اور ان کی دستاویزات درکار ہوں گی۔"))
            improvements.append({"en": "Add a sponsor with their bank statements, employment proof and a letter of support.",
                                 "ur": "اسپانسر شامل کریں: ان کے بینک اسٹیٹمنٹ، ملازمت کا ثبوت اور سپورٹ لیٹر۔"})

    # --- funds
    need = FUNDS_PER_DAY_PKR.get(d, 12_000) * trip.days * trip.travellers * 100
    funds = profile.funds_available_minor
    if funds is None:
        missing.append("funds_available")
    elif funds >= need * 2:
        factors.append(_f("funds_strong", "positive", 2, "Your available funds comfortably cover the trip.",
                          "آپ کی دستیاب رقم سفر کے اخراجات کے لیے کافی سے زیادہ ہے۔"))
    elif funds >= need:
        factors.append(_f("funds_ok", "positive", 1, "Your funds cover the trip, but without much margin.",
                          "آپ کی رقم سفر کے لیے کافی ہے، مگر زیادہ گنجائش نہیں۔"))
    else:
        factors.append(_f("funds_low", "negative", -2,
            "Your funds look low for this trip length. A refusal for insufficient funds is common.",
            "اس سفر کی مدت کے لحاظ سے آپ کی رقم کم لگتی ہے۔ ناکافی رقم پر ویزا مسترد ہونا عام ہے۔"))
        improvements.append({"en": "Shorten the trip, add a sponsor, or wait until your statements show steady savings. "
                                   "Never deposit borrowed money just before applying — sudden large deposits are a red flag.",
                             "ur": "سفر مختصر کریں، اسپانسر شامل کریں، یا انتظار کریں کہ اسٹیٹمنٹ میں مستقل بچت نظر آئے۔ "
                                   "درخواست سے پہلے ادھار رقم جمع نہ کروائیں — اچانک بڑی رقم جمع ہونا خطرے کی علامت ہے۔"})

    # --- travel history
    if strong_visas:
        factors.append(_f("travel_history_strong", "positive", 2,
            f"Previous travel to {', '.join(sorted(strong_visas))} with visas complied with is a strong positive.",
            f"پہلے {', '.join(sorted(strong_visas))} کا سفر اور ویزا شرائط کی پابندی ایک بڑا مثبت پہلو ہے۔"))
    elif visited - {"PK", ""}:
        factors.append(_f("travel_history_some", "positive", 1, "Some previous international travel helps.",
                          "پہلے کا بین الاقوامی سفر مددگار ہے۔"))
    else:
        factors.append(_f("no_travel_history", "negative", -1,
            "No previous travel history. Not a refusal reason on its own, but the rest of the file must be strong.",
            "پہلے کوئی سفر نہیں۔ صرف یہ مسترد ہونے کی وجہ نہیں، مگر باقی فائل مضبوط ہونی چاہیے۔"))
        if d in STRONG_TRAVEL:
            improvements.append({"en": "Consider a first trip to an easier destination (e.g. Malaysia, Türkiye, UAE) to build history.",
                                 "ur": "سفری ریکارڈ بنانے کے لیے پہلے کسی آسان ملک (مثلاً ملائیشیا، ترکیہ، یو اے ای) کا سفر کریں۔"})

    # --- refusals
    refusals = profile.prior_refusals
    same = [r for r in refusals if str(r.get("country", "")).upper() == d]
    if same:
        factors.append(_f("refused_same_country", "negative", -3,
            "You were refused by this country before. The new application must directly address the earlier refusal reasons, "
            "and you must declare the refusal — hiding it can lead to a ban.",
            "یہ ملک پہلے آپ کا ویزا مسترد کر چکا ہے۔ نئی درخواست میں پچھلی وجوہات کا براہِ راست جواب دینا ہوگا، اور "
            "انکار ظاہر کرنا لازمی ہے — چھپانے پر پابندی لگ سکتی ہے۔"))
    elif refusals:
        factors.append(_f("refused_elsewhere", "negative", -1, "A previous refusal elsewhere must be declared and explained.",
                          "کسی اور ملک سے پچھلا انکار ظاہر اور واضح کرنا ہوگا۔"))

    # --- ties
    ties = profile.ties_to_pakistan or {}
    if ties.get("property") or ties.get("family"):
        factors.append(_f("ties", "positive", 1, "Family and/or property in Pakistan show reasons to return.",
                          "پاکستان میں خاندان اور/یا جائیداد واپسی کی وجہ ظاہر کرتے ہیں۔"))
    if profile.sponsor and profile.sponsor.get("covers_costs"):
        factors.append(_f("sponsor", "positive", 1, "A sponsor covering costs helps if their documents are strong.",
                          "اخراجات اٹھانے والا اسپانسر مددگار ہے اگر ان کی دستاویزات مضبوط ہوں۔"))

    blockers = [f for f in factors if f.impact == "blocker"]
    score = sum(f.weight for f in factors)
    rating: Rating = "weak" if blockers or score < 0 else ("strong" if score >= 4 and not missing else "fair")

    requirements, citations = [], []
    for field in ("required_documents", "proof_of_funds", "gov_fee", "biometrics_required", "max_stay"):
        if field in facts:
            f = facts[field]
            requirements.append({"field": field, "value": f.value, "fresh": f.fresh, "citation": f.citation.model_dump()})
            citations.append(f.citation.model_dump())
    timeline = None
    if "processing_time" in facts:
        f = facts["processing_time"]
        timeline = {"processing_time": f.value, "fresh": f.fresh, "citation": f.citation.model_dump()}
        citations.append(f.citation.model_dump())
    uniq = list({c["url"]: c for c in citations}.values())
    return Assessment(rating=rating, score=score, factors=factors, improvements=improvements, blockers=blockers,
                      requirements=requirements, timeline=timeline, missing_info=missing, citations=uniq)


def assessment_card(a: Assessment, case_id: str | None = None) -> dict[str, Any]:
    return {"type": "assessment", "case_id": case_id, **a.model_dump()}
