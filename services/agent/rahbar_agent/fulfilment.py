"""Executors for irreversible bookings. Each requires an approved pending_action and verified payment."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from . import actions, cases, ledger
from .db import Jsonb
from .providers.flights import Pax, get_flight_provider
from .providers.hotels import Guest, get_hotel_provider


class FulfilmentError(ValueError):
    pass


def request_booking_confirmation(conn: Connection, case_id: str, user_id: str) -> dict[str, Any]:
    c = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
    if c is None or str(c["owner_id"]) != str(user_id):
        raise FulfilmentError("not found")
    kind = {"flight": "issue_ticket", "hotel": "book_hotel", "umrah_package": "book_umrah"}.get(c["service_type"])
    if kind is None:
        raise FulfilmentError("nothing to book")
    if c["status"] != "accepted" and not (c["service_type"] == "umrah_package" and c["status"] in ("collecting_documents", "documents_review")):
        raise FulfilmentError(f"case is {c['status']}")
    offer = c["trip"].get("offer") or {}
    summary = {
        "issue_ticket": (f"Issue the {offer.get('airline', '')} ticket ({', '.join(offer.get('flight_numbers', []))})",
                         f"{offer.get('airline', '')} ٹکٹ جاری کریں"),
        "book_hotel": (f"Book {offer.get('name', 'the hotel')} — cancellation: {offer.get('cancellation_en', '')}",
                       f"{offer.get('name', 'ہوٹل')} بک کریں — منسوخی: {offer.get('cancellation_ur', '')}"),
        "book_umrah": ("Book the Umrah package with our licensed partner (visa, flights, hotels, transport)",
                       "ہمارے لائسنس یافتہ پارٹنر کے ساتھ عمرہ پیکج بک کریں (ویزا، فلائٹ، ہوٹل، ٹرانسپورٹ)"),
    }[kind]
    decl = [{"code": "names_match_passport", "en": "Traveller names exactly match their passports.",
             "ur": "مسافروں کے نام پاسپورٹ کے عین مطابق ہیں۔"},
            {"code": "rules_read", "en": "I have read the cancellation/fare rules shown on each line.",
             "ur": "میں نے ہر لائن پر دیے گئے منسوخی/کرایہ کے قوانین پڑھ لیے ہیں۔"}]
    return actions.request_action(conn, case_id, kind, summary[0], summary[1], {"required_declarations": decl})


def issue_ticket(conn: Connection, case_id: str, action_id: str, ops_id: str) -> dict[str, Any]:
    actions.require_approved(conn, action_id, "issue_ticket", case_id)
    if not ledger.is_paid(conn, case_id):
        raise FulfilmentError("payment not verified")
    c = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
    pax = [Pax(full_name_as_passport=t["full_name_as_passport"]) for t in conn.execute(
        "select t.* from case_travellers ct join travellers t on t.id=ct.traveller_id where ct.case_id=%s", (case_id,))]
    if not pax:
        raise FulfilmentError("add travellers to the case first")
    prov = get_flight_provider()
    hold = prov.hold(c["trip"]["offer"]["offer_id"], pax)
    pay = conn.execute("select provider_ref from payments where case_id=%s and status='verified' limit 1", (case_id,)).fetchone()
    ticket = prov.issue(hold.hold_id, pay["provider_ref"])
    b = conn.execute(
        """insert into bookings (case_id, kind, provider, provider_ref, status, details, documents, idempotency_key)
           values (%s,'flight',%s,%s,'ticketed',%s,%s,%s) on conflict (idempotency_key) do nothing returning *""",
        (case_id, prov.name, ticket.pnr, Jsonb({"ticket_numbers": ticket.ticket_numbers, "offer": c["trip"]["offer"]}),
         Jsonb([{"name": f"e-ticket {ticket.pnr}", "kind": "e_ticket", "ticket_numbers": ticket.ticket_numbers}]),
         f"ticket:{action_id}"),
    ).fetchone()
    actions.mark_executed(conn, action_id, {"pnr": ticket.pnr})
    cases.transition(conn, case_id, "booked", actor_type="ops", actor_id=ops_id, event="booked", kind="Flight",
                     reference=ticket.pnr, data={"booking_id": str(b["id"]) if b else None})
    return b or {}


def book_hotel(conn: Connection, case_id: str, action_id: str, ops_id: str) -> dict[str, Any]:
    actions.require_approved(conn, action_id, "book_hotel", case_id)
    if not ledger.is_paid(conn, case_id):
        raise FulfilmentError("payment not verified")
    c = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
    guests = [Guest(full_name_as_passport=t["full_name_as_passport"]) for t in conn.execute(
        "select t.* from case_travellers ct join travellers t on t.id=ct.traveller_id where ct.case_id=%s", (case_id,))]
    prov = get_hotel_provider()
    pay = conn.execute("select provider_ref from payments where case_id=%s and status='verified' limit 1", (case_id,)).fetchone()
    hb = prov.book(c["trip"]["offer"]["offer_id"], guests, pay["provider_ref"])
    b = conn.execute(
        """insert into bookings (case_id, kind, provider, provider_ref, status, details, documents, idempotency_key)
           values (%s,'hotel',%s,%s,%s,%s,%s,%s) on conflict (idempotency_key) do nothing returning *""",
        (case_id, prov.name, hb.booking_ref, hb.status, Jsonb({"offer": c["trip"]["offer"]}),
         Jsonb([{"name": f"Hotel voucher {hb.booking_ref}", "kind": "voucher"}]), f"hotel:{action_id}"),
    ).fetchone()
    actions.mark_executed(conn, action_id, {"booking_ref": hb.booking_ref})
    cases.transition(conn, case_id, "booked", actor_type="ops", actor_id=ops_id, event="booked", kind="Hotel",
                     reference=hb.booking_ref)
    return b or {}


def record_partner_booking(conn: Connection, case_id: str, action_id: str, ops_id: str, *, partner_ref: str,
                           items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ManualPartnerAdapter: ops enter the partner's confirmation, visa status and vouchers."""
    actions.require_approved(conn, action_id, "book_umrah", case_id)
    if not ledger.is_paid(conn, case_id):
        raise FulfilmentError("payment not verified")
    if not partner_ref.strip():
        raise FulfilmentError("partner confirmation reference required")
    out = []
    for i, it in enumerate(items):
        if not it.get("reference"):
            raise FulfilmentError("every item needs its real reference (visa no., PNR, hotel confirmation)")
        b = conn.execute(
            """insert into bookings (case_id, kind, provider, provider_ref, status, details, documents, idempotency_key)
               values (%s,%s,'umrah_partner',%s,'confirmed',%s,%s,%s) on conflict (idempotency_key) do nothing returning *""",
            (case_id, it["kind"], it["reference"], Jsonb({"partner_ref": partner_ref, "description": it.get("description")}),
             Jsonb(it.get("documents", [])), f"umrah:{action_id}:{i}"),
        ).fetchone()
        if b:
            out.append(b)
            cases.add_event(conn, case_id, "partner", "booked", kind=it["kind"].replace("_", " ").title(), reference=it["reference"])
            for d in it.get("documents", []):
                cases.add_event(conn, case_id, "partner", "voucher_delivered", kind=it["kind"].replace("_", " ").title(),
                                name=d.get("name", "document"), data={"booking_id": str(b["id"])})
    actions.mark_executed(conn, action_id, {"partner_ref": partner_ref, "count": len(out)})
    cases.transition(conn, case_id, "booked", actor_type="ops", actor_id=ops_id, event="booked", kind="Umrah package",
                     reference=partner_ref)
    return out
