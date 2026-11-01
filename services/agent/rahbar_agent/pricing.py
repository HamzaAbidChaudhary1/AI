"""Itemised quotes (CLAUDE.md rule 3). Our service fee comes ONLY from the service_fees table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field, field_validator

from . import cases
from .config import get_settings
from .db import Jsonb
from .knowledge import PolicyFact
from .money import CURRENCIES, convert_minor, format_money

Kind = Literal["gov_fee", "vfs_fee", "flight", "hotel", "transport", "insurance", "ziyarat", "visa_fee", "other"]
Payee = Literal["government", "vfs", "tls", "airline", "hotel", "partner", "insurer", "transport"]


class QuoteItemIn(BaseModel):
    """A third-party cost line. The service fee is never accepted as input."""

    kind: Kind
    description_en: str
    description_ur: str
    unit_amount_minor: int = Field(ge=0)
    currency: str
    quantity: int = Field(default=1, ge=1)
    payee: Payee
    source_url: str | None = None
    source_verified_at: datetime | None = None
    indicative: bool = False           # not from verified/fresh official data or a live offer
    paid_directly_by_user: bool = False

    @field_validator("currency")
    @classmethod
    def _ccy(cls, v: str) -> str:
        if v not in CURRENCIES:
            raise ValueError("unsupported currency")
        return v


class QuoteError(ValueError):
    pass


def fx_table(conn: Connection, quote_currency: str = "PKR") -> dict[str, str]:
    if quote_currency != "PKR":
        raise QuoteError("quotes are issued in PKR in the MVP")
    return {r["currency"]: str(r["rate_to_pkr"]) for r in conn.execute("select currency, rate_to_pkr from fx_rates")}


def service_fee_row(conn: Connection, service_type: str, country: str | None) -> dict[str, Any]:
    row = conn.execute(
        """select * from service_fees where active and service_type=%s
             and (destination_country = %s or destination_country is null)
           order by destination_country nulls last limit 1""",
        (service_type, country),
    ).fetchone()
    if row is None:
        raise QuoteError(f"no service fee configured for {service_type}")
    return row


def items_from_policy(facts: dict[str, PolicyFact], travellers: int, country_label: str) -> list[QuoteItemIn]:
    """Government + application-centre fees from cited policy records."""
    out: list[QuoteItemIn] = []
    labels = {
        "gov_fee": ("gov_fee", "government", f"{country_label} government visa fee", f"{country_label} حکومتی ویزا فیس"),
        "service_centre_fee": ("vfs_fee", "vfs", "Visa application centre fee", "ویزا درخواست مرکز (VFS) فیس"),
    }
    for field, (kind, payee, en, ur) in labels.items():
        f = facts.get(field)
        if not f or not f.value or f.value.get("amount_minor") is None:
            continue
        if f.value["amount_minor"] == 0:
            continue
        out.append(QuoteItemIn(
            kind=kind, payee=payee, description_en=en, description_ur=ur,  # type: ignore[arg-type]
            unit_amount_minor=int(f.value["amount_minor"]), currency=f.value["currency"], quantity=travellers,
            source_url=f.citation.url, source_verified_at=datetime.fromisoformat(f.citation.verified_at),
            indicative=not f.usable_in_quote,
        ))
    return out


def build_quote(conn: Connection, case_id: str, items: list[QuoteItemIn], *, travellers: int = 1,
                valid_hours: int | None = None, valid_until: datetime | None = None,
                actor_type: str = "ai") -> dict[str, Any]:
    """Creates the next quote version for a case: third-party lines + our fee line, totals in PKR."""
    case = conn.execute("select * from cases where id=%s for update", (case_id,)).fetchone()
    if case is None:
        raise QuoteError("unknown case")
    fx = fx_table(conn)
    fee = service_fee_row(conn, case["service_type"], case["destination_country"])
    fee_qty = travellers if fee["per"] == "traveller" else 1
    lines: list[dict[str, Any]] = []
    for it in items:
        amount = it.unit_amount_minor * it.quantity
        lines.append({**it.model_dump(), "amount_minor": amount,
                      "amount_quote_currency_minor": convert_minor(amount, it.currency, "PKR", fx)})
    fee_amount = fee["amount_minor"] * fee_qty
    lines.append({
        "kind": "service_fee", "payee": "rahbar", "description_en": fee["description_en"],
        "description_ur": fee["description_ur"], "unit_amount_minor": fee["amount_minor"], "quantity": fee_qty,
        "currency": fee["currency"], "amount_minor": fee_amount,
        "amount_quote_currency_minor": convert_minor(fee_amount, fee["currency"], "PKR", fx),
        "source_url": None, "source_verified_at": None, "indicative": False, "paid_directly_by_user": False,
    })
    total = sum(ln["amount_quote_currency_minor"] for ln in lines)
    collect = sum(ln["amount_quote_currency_minor"] for ln in lines if not ln["paid_directly_by_user"])
    binding = not any(ln["indicative"] for ln in lines)
    s = get_settings()
    until = valid_until or datetime.now(UTC) + timedelta(hours=valid_hours or s.quote_valid_hours)
    version = conn.execute("select coalesce(max(version),0)+1 v from quotes where case_id=%s", (case_id,)).fetchone()["v"]
    conn.execute("update quotes set status='superseded' where case_id=%s and status in ('draft','sent')", (case_id,))
    used_fx = {ln["currency"]: fx[ln["currency"]] for ln in lines if ln["currency"] != "PKR"}
    q = conn.execute(
        """insert into quotes (case_id, version, valid_until, status, total_minor, currency, fx_rates, binding, collect_minor)
           values (%s,%s,%s,'sent',%s,'PKR',%s,%s,%s) returning *""",
        (case_id, version, until, total, Jsonb(used_fx), binding, collect),
    ).fetchone()
    for pos, ln in enumerate(lines):
        conn.execute(
            """insert into quote_line_items (quote_id, position, kind, description_en, description_ur, amount_minor, currency,
                 amount_quote_currency_minor, source_url, source_verified_at, payee, paid_directly_by_user, indicative,
                 quantity, unit_amount_minor)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (q["id"], pos, ln["kind"], ln["description_en"], ln["description_ur"], ln["amount_minor"], ln["currency"],
             ln["amount_quote_currency_minor"], ln["source_url"], ln["source_verified_at"], ln["payee"],
             ln["paid_directly_by_user"], ln["indicative"], ln["quantity"], ln["unit_amount_minor"]),
        )
    if case["status"] in ("consulting", "assessed", "quoted"):
        cases.transition(conn, case_id, "quoted", actor_type=actor_type, event="quoted", version=version,
                         total=format_money(total, "PKR"), data={"quote_id": str(q["id"])})
    return get_quote(conn, str(q["id"]))


def get_quote(conn: Connection, quote_id: str) -> dict[str, Any]:
    q = conn.execute("select * from quotes where id=%s", (quote_id,)).fetchone()
    if q is None:
        raise QuoteError("unknown quote")
    q["line_items"] = conn.execute("select * from quote_line_items where quote_id=%s order by position",
                                   (quote_id,)).fetchall()
    return q


def quote_card(q: dict[str, Any]) -> dict[str, Any]:
    """The 'quote' card streamed to the UI. Amounts only ever come from build_quote rows."""
    return {
        "type": "quote", "quote_id": str(q["id"]), "case_id": str(q["case_id"]), "version": q["version"],
        "currency": q["currency"], "total_minor": q["total_minor"], "collect_minor": q["collect_minor"],
        "binding": q["binding"], "valid_until": q["valid_until"].isoformat(), "fx_rates": q["fx_rates"],
        "status": q["status"],
        "lines": [{
            "kind": li["kind"], "description_en": li["description_en"], "description_ur": li["description_ur"],
            "amount_minor": li["amount_minor"], "currency": li["currency"], "quantity": li["quantity"],
            "amount_quote_currency_minor": li["amount_quote_currency_minor"], "payee": li["payee"],
            "source_url": li["source_url"],
            "source_verified_at": li["source_verified_at"].isoformat() if li["source_verified_at"] else None,
            "indicative": li["indicative"], "paid_directly_by_user": li["paid_directly_by_user"],
        } for li in q["line_items"]],
    }


def quote_amount_strings(card: dict[str, Any]) -> list[str]:
    """Amount strings the agent may mention in prose (guardrail allow-list)."""
    out = [format_money(card["total_minor"], card["currency"]), format_money(card["collect_minor"], card["currency"])]
    for ln in card["lines"]:
        out += [format_money(ln["amount_minor"], ln["currency"]), format_money(ln["amount_quote_currency_minor"], "PKR")]
    return out


def expire_quotes(conn: Connection) -> int:
    return conn.execute(
        "update quotes set status='expired' where status='sent' and valid_until < now()"
    ).rowcount


def accept_quote(conn: Connection, quote_id: str, user_id: str) -> dict[str, Any]:
    q = conn.execute("select q.*, c.owner_id, c.status as case_status, c.service_type from quotes q join cases c on c.id=q.case_id where q.id=%s for update",
                     (quote_id,)).fetchone()
    if q is None or str(q["owner_id"]) != str(user_id):
        raise QuoteError("not found")
    if q["status"] != "sent":
        raise QuoteError(f"quote is {q['status']}")
    if q["valid_until"] < datetime.now(UTC):
        conn.execute("update quotes set status='expired' where id=%s", (quote_id,))
        raise QuoteError("quote expired")
    if not q["binding"] and not get_settings().allow_test_data:
        raise QuoteError("quote is indicative; prices must be re-verified before it can be accepted")
    conn.execute("update quotes set status='accepted', accepted_at=now() where id=%s", (quote_id,))
    cases.transition(conn, str(q["case_id"]), "accepted", actor_type="user", actor_id=user_id,
                     event="quote_accepted", version=q["version"], data={"quote_id": quote_id})
    next_status = "collecting_documents" if q["service_type"] in ("visit_visa", "umrah_package") else None
    if next_status:
        cases.transition(conn, str(q["case_id"]), next_status, actor_type="system")
    return get_quote(conn, quote_id)
