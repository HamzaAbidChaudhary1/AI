"""Application pack generator + submission flow (docs/FULFILMENT.md "Visa application flow")."""

from __future__ import annotations

import importlib
from typing import Any

from psycopg import Connection

from . import actions, cases
from .db import Jsonb
from .i18n import country_name

SUPPORTED = {"GB": "gb", "TR": "tr"}


class PackError(ValueError):
    pass


def _ctx(conn: Connection, case: dict[str, Any]) -> list[dict[str, Any]]:
    travellers = conn.execute(
        """select t.*, tp.employment_status, tp.employer, tp.monthly_income_minor, tp.travel_history, tp.prior_refusals,
                  tp.sponsor, tp.ties_to_pakistan
           from case_travellers ct join travellers t on t.id=ct.traveller_id
           left join traveller_profiles tp on tp.traveller_id=t.id where ct.case_id=%s order by t.created_at""",
        (case["id"],)).fetchall()
    docs = conn.execute("select * from documents where case_id=%s and deleted_at is null", (case["id"],)).fetchall()
    out = []
    for t in travellers:
        mine = {d["doc_type"]: d.get("extracted") or {} for d in docs if d["traveller_id"] in (None, t["id"])}
        prof = {k: t.get(k) for k in ("employment_status", "employer", "monthly_income_minor", "travel_history",
                                      "prior_refusals", "sponsor", "ties_to_pakistan")}
        prof["travel_history"] = prof["travel_history"] or []
        prof["prior_refusals"] = prof["prior_refusals"] or []
        out.append({"traveller": t, "profile": prof, "docs": mine, "trip": {**case["trip"], "purpose": case["purpose"]}})
    return out


def cover_letter(case: dict[str, Any], ctx: dict[str, Any]) -> str:
    t, prof, trip = ctx["traveller"], ctx["profile"], ctx["trip"]
    emp = prof.get("employer") or ctx["docs"].get("employment_letter", {}).get("employer")
    lines = [
        "To the Visa Officer,",
        "",
        f"I, {t['full_name_as_passport']}, a citizen of Pakistan, am applying for a visit visa to {country_name(case['destination_country'])} "
        f"for {trip.get('purpose') or 'tourism'}" + (f" from {trip['depart_date']} to {trip['return_date']}." if trip.get("depart_date") and trip.get("return_date") else "."),
    ]
    if emp:
        lines.append(f"I am currently {prof.get('employment_status', 'employed').replace('_', ' ')} with {emp}, and I will return to my work in Pakistan after the trip.")
    if prof.get("prior_refusals"):
        lines.append("I was previously refused a visa; I have declared this in my application and the enclosed documents address the earlier concerns.")
    lines += ["", "My itinerary, financial documents and evidence of my ties to Pakistan are enclosed as listed in the document index.",
              "", "Yours faithfully,", t["full_name_as_passport"]]
    return "\n".join(lines)


def generate_application_pack(conn: Connection, case_id: str) -> dict[str, Any]:
    case = conn.execute("select * from cases where id=%s for update", (case_id,)).fetchone()
    if case is None:
        raise PackError("unknown case")
    if case["status"] != "documents_review":
        raise PackError(f"case is {case['status']}; documents must pass review first")
    blockers = conn.execute(
        "select count(*) n from documents where case_id=%s and deleted_at is null and review_status in ('issues','rejected','pending')",
        (case_id,)).fetchone()["n"]
    if blockers:
        raise PackError("documents still have open issues")
    code = SUPPORTED.get(case["destination_country"] or "")
    if not code:
        raise PackError(f"application packs are not available yet for {case['destination_country']}")
    mapper = importlib.import_module(f".forms.{code}", __package__)
    docs = conn.execute("select id, doc_type, traveller_id, mime, sha256 from documents where case_id=%s and deleted_at is null order by doc_type",
                        (case_id,)).fetchall()
    applicants = []
    for ctx in _ctx(conn, case):
        applicants.append({"traveller_id": str(ctx["traveller"]["id"]), "name": ctx["traveller"]["full_name_as_passport"],
                           "form_data": mapper.map_fields(ctx), "cover_letter_en": cover_letter(case, ctx)})
    content = {
        "destination": case["destination_country"], "portal": code, "applicants": applicants,
        "itinerary": case["trip"].get("itinerary") or [{"day": 1, "plan": "Arrival"}, {"day": int(case["trip"].get("days", 7)), "plan": "Return to Pakistan"}],
        "document_index": [{"n": i + 1, "doc_type": d["doc_type"], "document_id": str(d["id"]),
                            "filename": f"{i + 1:02d}_{d['doc_type']}"} for i, d in enumerate(docs)],
        "biometrics_checklist": mapper.BIOMETRICS,
        "declarations": mapper.DECLARATIONS,
    }
    version = conn.execute("select coalesce(max(version),0)+1 v from application_packs where case_id=%s", (case_id,)).fetchone()["v"]
    pack = conn.execute("insert into application_packs (case_id, version, content) values (%s,%s,%s) returning *",
                        (case_id, version, Jsonb(content))).fetchone()
    cases.transition(conn, case_id, "pack_ready", actor_type="ai", event="pack_ready", data={"pack_id": str(pack["id"])})
    return pack


def latest_pack(conn: Connection, case_id: str) -> dict[str, Any] | None:
    return conn.execute("select * from application_packs where case_id=%s order by version desc limit 1", (case_id,)).fetchone()


def request_submission(conn: Connection, case_id: str, user_id: str) -> dict[str, Any]:
    case = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
    if case is None or str(case["owner_id"]) != str(user_id):
        raise PackError("not found")
    if case["status"] not in ("pack_ready", "awaiting_user_confirmation"):
        raise PackError(f"case is {case['status']}")
    pack = latest_pack(conn, case_id)
    if pack is None:
        raise PackError("no pack")
    name = country_name(case["destination_country"])
    a = actions.request_action(
        conn, case_id, "submit_visa",
        f"Submit the {name} visa application (pack v{pack['version']}) on the official portal",
        f"{country_name(case['destination_country'], 'ur')} ویزا درخواست (پیک v{pack['version']}) سرکاری پورٹل پر جمع کروائیں",
        {"pack_id": str(pack["id"]), "required_declarations": pack["content"]["declarations"]},
    )
    if case["status"] == "pack_ready":
        cases.transition(conn, case_id, "awaiting_user_confirmation", actor_type="ai")
    return a


def record_submission(conn: Connection, case_id: str, action_id: str, ops_id: str, reference: str,
                      portal: str) -> dict[str, Any]:
    """Ops entered the application on the portal; store the REAL reference and show it to the user."""
    if not reference.strip():
        raise PackError("reference number required")
    actions.require_approved(conn, action_id, "submit_visa", case_id)
    b = conn.execute(
        """insert into bookings (case_id, kind, provider, provider_ref, status, details, idempotency_key)
           values (%s,'visa_application',%s,%s,'submitted',%s,%s)
           on conflict (idempotency_key) do update set provider_ref=excluded.provider_ref returning *""",
        (case_id, portal, reference.strip(), Jsonb({"action_id": action_id}), f"submit:{action_id}"),
    ).fetchone()
    actions.mark_executed(conn, action_id, {"reference": reference.strip(), "booking_id": str(b["id"])})
    cases.transition(conn, case_id, "submitted", actor_type="ops", actor_id=ops_id, event="submitted",
                     reference=reference.strip(), data={"booking_id": str(b["id"])})
    return b
