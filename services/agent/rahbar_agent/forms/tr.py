"""Türkiye e-Visa (evisa.gov.tr) field mapping."""

from __future__ import annotations

from typing import Any

from .base import common_identity, field


def map_fields(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    trip, prof = ctx["trip"], ctx["profile"]
    supporting = next((h for h in prof.get("travel_history", []) if str(h.get("country", "")).upper() in
                       {"GB", "US", "IE", "DE", "FR", "IT", "ES", "NL"}), None)
    out = common_identity(ctx)
    out += [
        field("Travel", "Arrival date", trip.get("depart_date", ""), "case"),
        field("Travel", "Travel document type", "Ordinary passport", "fixed"),
        field("Supporting document", "Supporting visa/residence permit", f"{supporting['country']} visa" if supporting else "MISSING", "profile"),
        field("Contact", "Address in Pakistan", "[from traveller profile]", "traveller"),
    ]
    return out


DECLARATIONS = [
    {"code": "truthful", "en": "All information I gave is true and complete.", "ur": "میری دی گئی تمام معلومات درست اور مکمل ہیں۔"},
    {"code": "supporting_visa_valid", "en": "My supporting visa/residence permit is valid on my arrival date.",
     "ur": "میرا معاون ویزا/رہائشی اجازت نامہ میری آمد کی تاریخ پر درست ہے۔"},
    {"code": "no_guarantee", "en": "I understand Rahbar cannot guarantee a visa; the Turkish authorities decide.",
     "ur": "میں سمجھتا/سمجھتی ہوں کہ رہبر ویزا کی ضمانت نہیں دے سکتا؛ فیصلہ ترک حکام کرتے ہیں۔"},
]
BIOMETRICS: list[str] = []
