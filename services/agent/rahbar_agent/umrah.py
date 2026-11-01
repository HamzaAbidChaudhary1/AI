"""Umrah package builder (PRD J2) + quote items for flight/hotel offers.

Options are assembled only from partner inventory entered by ops. Every line has a payee and a
price source; hotel distance to the Haram is labelled "as provided by partner"."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .pricing import QuoteItemIn
from .providers.umrah import ManualPartnerAdapter

TIERS = [
    ("economy", 3, "Economy", "اکانومی"),
    ("standard", 4, "Standard", "اسٹینڈرڈ"),
    ("premium", 5, "Near Haram", "حرم کے قریب"),
]


def _line(item: dict[str, Any], qty: int, travellers: int) -> dict[str, Any]:
    return {
        "kind": item["kind"], "name": item["name"], "unit_amount_minor": item["unit_amount_minor"],
        "currency": item["currency"], "quantity": qty, "amount_minor": item["unit_amount_minor"] * qty,
        "per": item["per"], "details": item["details"], "partner": item["partner_name"],
        "partner_licence": item["licence_number"], "inventory_id": str(item["id"]),
        "price_updated_at": (item.get("updated_at") or item["created_at"]).isoformat(),
    }


def build_options(start: date, nights_makkah: int, nights_madinah: int, travellers: int,
                  origin: str = "LHE") -> list[dict[str, Any]]:
    end = start + timedelta(days=nights_makkah + nights_madinah)
    inv = ManualPartnerAdapter().get_inventory(start, end, travellers)
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for it in inv:
        by_kind.setdefault(it["kind"], []).append(it)
    required = ("visa", "hotel_makkah", "hotel_madinah", "transport")
    if not all(by_kind.get(k) for k in required):
        return []
    options = []
    for code, stars, en, ur in TIERS:
        mk = next((h for h in by_kind["hotel_makkah"] if h["details"].get("stars") == stars), None)
        md = next((h for h in by_kind["hotel_madinah"] if h["details"].get("stars") == stars), None)
        if not mk or not md:
            continue
        lines = [_line(by_kind["visa"][0], travellers, travellers)]
        if by_kind.get("flight"):
            lines.append(_line(by_kind["flight"][0], travellers, travellers))
        lines.append(_line(mk, travellers * nights_makkah, travellers))
        lines.append(_line(md, travellers * nights_madinah, travellers))
        lines.append(_line(by_kind["transport"][0], travellers, travellers))
        if by_kind.get("ziyarat"):
            lines.append(_line(by_kind["ziyarat"][0], travellers, travellers))
        options.append({
            "code": code, "label_en": f"{en} ({stars}★ hotels)", "label_ur": f"{ur} ({stars}★ ہوٹل)",
            "start": start.isoformat(), "end": end.isoformat(), "origin": origin, "travellers": travellers,
            "nights_makkah": nights_makkah, "nights_madinah": nights_madinah,
            "partner_id": str(mk["partner_id"]), "partner_name": mk["partner_name"],
            "partner_licence": mk["licence_number"], "partner_licence_authority": mk["licence_authority"],
            "makkah_distance_m": mk["details"].get("distance_to_haram_m"),
            "madinah_distance_m": md["details"].get("distance_to_haram_m"),
            "distance_source": "as provided by partner",
            "lines": lines, "total_minor": sum(li["amount_minor"] for li in lines), "currency": "PKR",
            "citation": {"url": f"partner:{mk['partner_id']}", "title": f"Price list: {mk['partner_name']}",
                         "authority": f"{mk['partner_name']} (licence {mk['licence_number']})",
                         "verified_at": max(li["price_updated_at"] for li in lines), "is_test_fixture":
                         "demo" in (mk["partner_name"] or "").lower()},
        })
    return options


_KIND_MAP = {"visa": ("visa_fee", "partner"), "flight": ("flight", "airline"), "hotel_makkah": ("hotel", "hotel"),
             "hotel_madinah": ("hotel", "hotel"), "transport": ("transport", "partner"), "ziyarat": ("ziyarat", "partner"),
             "insurance": ("insurance", "insurer")}
_UR = {"visa": "عمرہ ویزا اور لازمی انشورنس (پارٹنر کے ذریعے)", "flight": "واپسی کی فلائٹ",
       "hotel_makkah": "مکہ ہوٹل", "hotel_madinah": "مدینہ ہوٹل", "transport": "ٹرانسپورٹ", "ziyarat": "زیارات"}


def option_quote_items(opt: dict[str, Any]) -> list[QuoteItemIn]:
    items = []
    for li in opt["lines"]:
        kind, payee = _KIND_MAP[li["kind"]]
        items.append(QuoteItemIn(
            kind=kind, payee=payee,  # type: ignore[arg-type]
            description_en=f"{li['name']} — via {li['partner']} (licence {li['partner_licence']})",
            description_ur=f"{_UR.get(li['kind'], li['name'])} — {li['partner']} کے ذریعے (لائسنس {li['partner_licence']})",
            unit_amount_minor=li["unit_amount_minor"], quantity=li["quantity"], currency=li["currency"],
        ))
    return items


def offer_quote_items(kind: str, offer: dict[str, Any]) -> list[QuoteItemIn]:
    sandbox = offer.get("provider") == "sandbox"
    if kind == "flight":
        flights = ", ".join(offer["flight_numbers"])
        return [
            QuoteItemIn(kind="flight", payee="airline", description_en=f"{offer['airline']} fare ({flights})",
                        description_ur=f"{offer['airline']} کرایہ ({flights})", unit_amount_minor=offer["fare_minor"],
                        currency=offer["currency"], indicative=sandbox),
            QuoteItemIn(kind="flight", payee="airline", description_en="Airport taxes and charges",
                        description_ur="ایئرپورٹ ٹیکس اور چارجز", unit_amount_minor=offer["taxes_minor"],
                        currency=offer["currency"], indicative=sandbox),
        ]
    return [QuoteItemIn(kind="hotel", payee="hotel", description_en=f"{offer['name']} — {offer['nights']} nights, {offer['room']}",
                        description_ur=f"{offer['name']} — {offer['nights']} راتیں", unit_amount_minor=offer["total_minor"],
                        currency=offer["currency"], indicative=sandbox)]
