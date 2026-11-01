"""UK Standard Visitor (gov.uk Access UK) field mapping."""

from __future__ import annotations

from typing import Any

from .base import common_identity, field


def map_fields(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    prof, trip, bs = ctx["profile"], ctx["trip"], ctx["docs"].get("bank_statement", {})
    out = common_identity(ctx)
    out += [
        field("Your visit", "Main reason for visit", (trip.get("purpose") or "Tourism").capitalize(), "case"),
        field("Your visit", "Date you plan to arrive", trip.get("depart_date", ""), "case"),
        field("Your visit", "Date you plan to leave", trip.get("return_date", ""), "case"),
        field("Employment", "Employment status", prof.get("employment_status", ""), "profile"),
        field("Employment", "Employer", prof.get("employer") or ctx["docs"].get("employment_letter", {}).get("employer", ""), "profile/letter"),
        field("Money", "Monthly income after tax (PKR)", (prof.get("monthly_income_minor") or 0) // 100, "profile"),
        field("Money", "Money in bank (PKR)", bs.get("closing_balance", ""), "bank statement"),
        field("Travel history", "Visits to UK/USA/Canada/Australia/NZ/Schengen in last 10 years",
              ", ".join(f"{h.get('country')} {h.get('year', '')}".strip() for h in prof.get("travel_history", [])) or "None", "profile"),
        field("Travel history", "Have you ever been refused a visa?",
              "Yes — " + "; ".join(f"{r.get('country')} {r.get('year', '')}" for r in prof.get("prior_refusals", []))
              if prof.get("prior_refusals") else "No", "profile"),
    ]
    return out


DECLARATIONS = [
    {"code": "truthful", "en": "All information I gave is true and complete. I understand false information can lead to refusal and a ban of up to 10 years.",
     "ur": "میری دی گئی تمام معلومات درست اور مکمل ہیں۔ میں سمجھتا/سمجھتی ہوں کہ غلط معلومات پر انکار اور 10 سال تک پابندی ہو سکتی ہے۔"},
    {"code": "refusals_declared", "en": "I have declared every previous visa refusal, from any country.",
     "ur": "میں نے کسی بھی ملک سے ہر سابقہ ویزا انکار ظاہر کر دیا ہے۔"},
    {"code": "documents_genuine", "en": "Every document is genuine and unaltered.", "ur": "ہر دستاویز اصل ہے اور اس میں کوئی ترمیم نہیں۔"},
    {"code": "no_guarantee", "en": "I understand Rahbar cannot guarantee a visa; UK Visas and Immigration decides.",
     "ur": "میں سمجھتا/سمجھتی ہوں کہ رہبر ویزا کی ضمانت نہیں دے سکتا؛ فیصلہ (UK Visas and Immigration) کرتا ہے۔"},
]
BIOMETRICS = ["Original passport and all old passports", "Printed appointment confirmation", "Printed application/checklist",
              "Original supporting documents in the order of the document index"]
