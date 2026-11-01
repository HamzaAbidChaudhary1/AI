"""Form mapper contract: one mapper per destination portal (docs/FULFILMENT.md)."""

from __future__ import annotations

from typing import Any

SENSITIVE = "[shown to ops only — fetched on demand, access logged]"


def field(section: str, label: str, value: Any, source: str) -> dict[str, Any]:
    return {"section": section, "label": label, "value": value, "source": source}


def common_identity(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    t, p = ctx["traveller"], ctx["docs"].get("passport", {})
    return [
        field("Personal details", "Full name (as in passport)", t["full_name_as_passport"], "traveller"),
        field("Personal details", "Date of birth", str(t.get("date_of_birth") or p.get("date_of_birth") or ""), "traveller/passport"),
        field("Personal details", "Gender", t.get("gender") or "", "traveller"),
        field("Personal details", "Nationality", "Pakistani", "traveller"),
        field("Passport", "Passport number", SENSITIVE, "encrypted"),
        field("Passport", "Passport expiry", str(t.get("passport_expiry") or p.get("expiry_date") or ""), "traveller/passport"),
        field("Passport", "Issuing authority", "Directorate General of Immigration & Passports, Pakistan", "fixed"),
    ]
