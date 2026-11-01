"""Payments ledger: manual bank transfer + receipt verification, refunds by policy (docs/FULFILMENT.md)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection

from . import actions, cases
from .db import Jsonb
from .money import format_money
from .providers.payments import get_payment_provider

ORDER = ["consulting", "assessed", "quoted", "accepted", "collecting_documents", "documents_review", "pack_ready",
         "awaiting_user_confirmation", "submitted", "biometrics_scheduled", "in_process", "decision_approved",
         "decision_refused", "booked", "completed"]


class PaymentError(ValueError):
    pass


def create_payment_request(conn: Connection, quote_id: str, user_id: str) -> dict[str, Any]:
    q = conn.execute("select q.*, c.owner_id from quotes q join cases c on c.id=q.case_id where q.id=%s", (quote_id,)).fetchone()
    if q is None or str(q["owner_id"]) != str(user_id):
        raise PaymentError("not found")
    if q["status"] != "accepted":
        raise PaymentError("accept the quote first")
    existing = conn.execute("select * from payments where quote_id=%s and direction='in' and status <> 'failed'",
                            (quote_id,)).fetchone()
    if existing:
        return existing
    req = get_payment_provider().create_payment_request(q, idempotency_key=uuid.uuid4().hex)
    p = conn.execute(
        """insert into payments (case_id, quote_id, provider, provider_ref, amount_minor, currency, status, idempotency_key)
           values (%s,%s,%s,%s,%s,%s,'pending',%s) returning *""",
        (q["case_id"], quote_id, req["provider"], req["reference"], req["amount_minor"], req["currency"], f"pay:{quote_id}"),
    ).fetchone()
    cases.add_event(conn, q["case_id"], "system", "payment_requested", amount=format_money(req["amount_minor"], req["currency"]),
                    data={"payment_id": str(p["id"]), "instructions": req["instructions"]})
    p["instructions"] = req["instructions"]
    return p


def attach_receipt(conn: Connection, payment_id: str, user_id: str, receipt_path: str) -> dict[str, Any]:
    p = conn.execute("select p.*, c.owner_id from payments p join cases c on c.id=p.case_id where p.id=%s for update",
                     (payment_id,)).fetchone()
    if p is None or str(p["owner_id"]) != str(user_id):
        raise PaymentError("not found")
    if p["status"] not in ("pending", "received"):
        raise PaymentError(f"payment is {p['status']}")
    conn.execute("update payments set status='received', receipt_path=%s where id=%s", (receipt_path, payment_id))
    conn.execute("insert into ops_tasks (kind, case_id, payload) values ('verify_payment', %s, %s)",
                 (p["case_id"], Jsonb({"payment_id": payment_id})))
    cases.add_event(conn, p["case_id"], "user", "payment_receipt", actor_id=user_id, data={"payment_id": payment_id})
    return conn.execute("select * from payments where id=%s", (payment_id,)).fetchone()


def verify_payment(conn: Connection, payment_id: str, ops_id: str, bank_reference: str) -> dict[str, Any]:
    p = conn.execute("select * from payments where id=%s for update", (payment_id,)).fetchone()
    if p is None or p["status"] != "received":
        raise PaymentError("payment is not awaiting verification")
    if not bank_reference.strip():
        raise PaymentError("bank reference required")
    conn.execute("update payments set status='verified', provider_ref=%s where id=%s", (bank_reference.strip(), payment_id))
    conn.execute("update ops_tasks set status='done', resolved_by=%s, resolved_at=now() where kind='verify_payment' and payload->>'payment_id'=%s",
                 (ops_id, payment_id))
    cases.add_event(conn, p["case_id"], "ops", "payment_verified", actor_id=ops_id,
                    amount=format_money(p["amount_minor"], p["currency"]), reference=bank_reference.strip(),
                    data={"payment_id": payment_id})
    return conn.execute("select * from payments where id=%s", (payment_id,)).fetchone()


def is_paid(conn: Connection, case_id: str) -> bool:
    return bool(conn.execute("select 1 from payments where case_id=%s and direction='in' and status='verified'", (case_id,)).fetchone())


def refund_quote(conn: Connection, case_id: str) -> dict[str, Any]:
    """What the published refund policy allows right now (our service fee only; third-party rules shown per line)."""
    case = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
    pol = conn.execute("select * from refund_policies where service_type=%s", (case["service_type"],)).fetchone()
    q = conn.execute("select * from quotes where case_id=%s and status='accepted' order by version desc limit 1", (case_id,)).fetchone()
    if not pol or not q:
        return {"refundable_minor": 0, "percent": 0, "currency": "PKR"}
    fee = conn.execute("select coalesce(sum(amount_quote_currency_minor),0) s from quote_line_items where quote_id=%s and kind='service_fee'",
                       (q["id"],)).fetchone()["s"]
    status = case["status"]
    idx = ORDER.index(status) if status in ORDER else len(ORDER)
    pct = 0
    for rule in pol["rules"]:
        b = rule.get("before_status")
        if b is None or (b in ORDER and idx < ORDER.index(b)):
            pct = rule["refund_percent"]
            break
    return {"refundable_minor": int(fee) * pct // 100, "percent": pct, "currency": "PKR",
            "policy_en": pol["text_en"], "policy_ur": pol["text_ur"], "status": status}


def issue_refund(conn: Connection, case_id: str, action_id: str, ops_id: str, amount_minor: int, reason: str) -> dict[str, Any]:
    actions.require_approved(conn, action_id, "refund", case_id)
    if not reason.strip():
        raise PaymentError("reason required")
    r = conn.execute(
        """insert into payments (case_id, provider, amount_minor, currency, status, direction, reason, idempotency_key)
           values (%s,'manual_bank_transfer',%s,'PKR','refunded','refund',%s,%s)
           on conflict (idempotency_key) do nothing returning *""",
        (case_id, amount_minor, reason, f"refund:{action_id}"),
    ).fetchone()
    actions.mark_executed(conn, action_id, {"amount_minor": amount_minor})
    cases.add_event(conn, case_id, "ops", "refund_issued", actor_id=ops_id, amount=format_money(amount_minor, "PKR"),
                    reason=reason, data={"payment_id": str(r["id"]) if r else None})
    st = conn.execute("select status from cases where id=%s", (case_id,)).fetchone()["status"]
    if st != "refunded":
        if "refunded" not in cases.TRANSITIONS.get(st, set()):
            cases.transition(conn, case_id, "cancelled", actor_type="ops", actor_id=ops_id, event="cancelled", reason=reason)
        cases.transition(conn, case_id, "refunded", actor_type="ops", actor_id=ops_id)
    return r or {}
