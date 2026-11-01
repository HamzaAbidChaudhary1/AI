"""Ops console API (/ops). Role-gated (ops/admin, 2FA). Every action audited and logged to case_events."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from rahbar_agent import actions, cases, crypto, fulfilment, jobs, ledger, packs
from rahbar_agent.cases import TransitionError
from rahbar_agent.crawl.providers import domain_allowed
from rahbar_agent.db import Jsonb, tx

from .auth import User, admin_user, staff_user
from .routes_customer import case_bundle
from .security import audit

router = APIRouter(prefix="/ops")


def _409(e: Exception) -> HTTPException:
    return HTTPException(409, str(e))


@router.get("/cases")
def queue(status: str | None = None, service: str | None = None, sla_breach: bool = False,
          user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute(
            """select * from (
                 select c.id, c.service_type, c.destination_country, c.status, c.strength_rating, c.created_at, c.updated_at,
                        p.full_name as customer, c.assigned_ops_id,
                        (select count(*) from ops_tasks t where t.case_id=c.id and t.status='open') as open_tasks,
                        (coalesce(c.updated_at, c.created_at) < now() - interval '48 hours'
                          and c.status not in ('completed','cancelled','refunded','in_process','submitted')) as sla_breach
                 from cases c join profiles p on p.id=c.owner_id
                 where (%s::text is null or c.status::text=%s) and (%s::text is null or c.service_type::text=%s)) q
               where (not %s or q.sla_breach)
               order by q.open_tasks desc, q.sla_breach desc, coalesce(q.updated_at, q.created_at) desc limit 200""",
            (status, status, service, service, sla_breach)).fetchall()


@router.get("/cases/{case_id}")
def case_detail(case_id: str, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        c = conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
        if c is None:
            raise HTTPException(404, "not found")
        audit(conn, user.id, user.role, "view_case", "case", case_id)
        b = case_bundle(conn, c, staff=True)
        b["tasks"] = conn.execute("select * from ops_tasks where case_id=%s order by created_at desc", (case_id,)).fetchall()
        b["usage"] = conn.execute("select model, sum(input_tokens) i, sum(output_tokens) o from llm_usage where case_id=%s group by model",
                                  (case_id,)).fetchall()
        return b


@router.get("/tasks")
def tasks(kind: str | None = None, user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute("select * from ops_tasks where status='open' and (%s::text is null or kind=%s) order by created_at",
                            (kind, kind)).fetchall()


@router.get("/travellers/{traveller_id}/sensitive")
def reveal(traveller_id: str, case_id: str, user: User = Depends(staff_user)) -> dict[str, Any]:
    """Decrypted passport/CNIC for manual portal entry. Every access is audit-logged with the case."""
    with tx() as conn:
        t = conn.execute("""select t.* from travellers t join case_travellers ct on ct.traveller_id=t.id
                            where t.id=%s and ct.case_id=%s""", (traveller_id, case_id)).fetchone()
        if t is None:
            raise HTTPException(404, "not found")
        audit(conn, user.id, user.role, "reveal_ids", "traveller", traveller_id, {"case_id": case_id})
        return {"passport_number": crypto.decrypt(t["passport_number_enc"]) if t["passport_number_enc"] else None,
                "cnic": crypto.decrypt(t["cnic_enc"]) if t["cnic_enc"] else None}


class Approve(BaseModel):
    approve: bool = True
    reason: str | None = Field(default=None, max_length=500)


@router.post("/actions/{action_id}/approve")
def approve(action_id: str, body: Approve, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        try:
            a = actions.approve_by_ops(conn, action_id, user.id, approve=body.approve, reason=body.reason)
        except actions.ActionNotApproved as e:
            raise _409(e) from e
        audit(conn, user.id, user.role, "approve_action" if body.approve else "reject_action", "pending_action", action_id)
        return actions.confirm_card(a)


class Submission(BaseModel):
    action_id: str
    reference: str = Field(min_length=4, max_length=64)
    portal: str = Field(max_length=64)


@router.post("/cases/{case_id}/submission")
def submission(case_id: str, body: Submission, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        try:
            b = packs.record_submission(conn, case_id, body.action_id, user.id, body.reference, body.portal)
        except (actions.ActionNotApproved, packs.PackError, TransitionError) as e:
            raise _409(e) from e
        audit(conn, user.id, user.role, "record_submission", "case", case_id, {"portal": body.portal})
        return b


class StatusUpdate(BaseModel):
    status: Literal["biometrics_scheduled", "in_process", "decision_approved", "decision_refused", "completed", "cancelled"]
    when: str | None = None
    where: str | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.post("/cases/{case_id}/status")
def update_status(case_id: str, body: StatusUpdate, user: User = Depends(staff_user)) -> dict[str, Any]:
    ev = {"biometrics_scheduled": "biometrics_scheduled", "in_process": "in_process", "decision_approved": "decision_approved",
          "decision_refused": "decision_refused", "completed": "completed", "cancelled": "cancelled"}[body.status]
    fmt: dict[str, Any] = {}
    if body.status == "biometrics_scheduled":
        if not body.when or not body.where:
            raise HTTPException(422, "when and where are required")
        fmt = {"when": body.when, "where": body.where}
        jobs.enqueue("send_notification", {"case_id": case_id, "kind": "biometrics_reminder", "when": body.when})
    if body.status == "cancelled":
        fmt = {"reason": body.note or ""}
    with tx() as conn:
        try:
            c = cases.transition(conn, case_id, body.status, actor_type="ops", actor_id=user.id, event=ev, **fmt)
        except TransitionError as e:
            raise _409(e) from e
        audit(conn, user.id, user.role, "status", "case", case_id, {"to": body.status})
        return c


class Note(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    visible_to_user: bool = False


@router.post("/cases/{case_id}/notes")
def add_note(case_id: str, body: Note, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        return cases.add_event(conn, case_id, "ops", "ops_note", actor_id=user.id, visible=body.visible_to_user, note=body.note)


class Verify(BaseModel):
    bank_reference: str = Field(min_length=3, max_length=64)


@router.post("/payments/{payment_id}/verify")
def verify_payment(payment_id: str, body: Verify, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        try:
            p = ledger.verify_payment(conn, payment_id, user.id, body.bank_reference)
        except ledger.PaymentError as e:
            raise _409(e) from e
        audit(conn, user.id, user.role, "verify_payment", "payment", payment_id)
        return p


class Exec(BaseModel):
    action_id: str


@router.post("/cases/{case_id}/issue-ticket")
def issue_ticket(case_id: str, body: Exec, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        try:
            return fulfilment.issue_ticket(conn, case_id, body.action_id, user.id)
        except (actions.ActionNotApproved, fulfilment.FulfilmentError, TransitionError) as e:
            raise _409(e) from e


@router.post("/cases/{case_id}/book-hotel")
def book_hotel(case_id: str, body: Exec, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        try:
            return fulfilment.book_hotel(conn, case_id, body.action_id, user.id)
        except (actions.ActionNotApproved, fulfilment.FulfilmentError, TransitionError) as e:
            raise _409(e) from e


class PartnerItem(BaseModel):
    kind: Literal["visa_application", "flight", "hotel", "transport", "insurance"]
    reference: str = Field(min_length=3, max_length=64)
    description: str | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)


class PartnerBooking(BaseModel):
    action_id: str
    partner_ref: str = Field(min_length=3, max_length=64)
    items: list[PartnerItem]


@router.post("/cases/{case_id}/partner-booking")
def partner_booking(case_id: str, body: PartnerBooking, user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        try:
            out = fulfilment.record_partner_booking(conn, case_id, body.action_id, user.id, partner_ref=body.partner_ref,
                                                    items=[i.model_dump() for i in body.items])
        except (actions.ActionNotApproved, fulfilment.FulfilmentError, TransitionError) as e:
            raise _409(e) from e
        audit(conn, user.id, user.role, "partner_booking", "case", case_id)
        return out


class RefundIn(BaseModel):
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/cases/{case_id}/refund")
def request_refund(case_id: str, body: RefundIn, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        allowed = ledger.refund_quote(conn, case_id)
        a = actions.request_ops_action(conn, case_id, "refund", f"Refund PKR {body.amount_minor // 100:,}: {body.reason}",
                                       f"واپسی PKR {body.amount_minor // 100:,}: {body.reason}",
                                       {"amount_minor": body.amount_minor, "reason": body.reason, "policy": allowed}, user.id)
        audit(conn, user.id, user.role, "refund_requested", "case", case_id, {"amount_minor": body.amount_minor})
        return {"action": actions.confirm_card(a), "policy_allows": allowed}


@router.post("/cases/{case_id}/refund/{action_id}/execute")
def execute_refund(case_id: str, action_id: str, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        a = conn.execute("select payload from pending_actions where id=%s", (action_id,)).fetchone()
        if a is None:
            raise HTTPException(404, "not found")
        try:
            return ledger.issue_refund(conn, case_id, action_id, user.id, a["payload"]["amount_minor"], a["payload"]["reason"])
        except (actions.ActionNotApproved, ledger.PaymentError, TransitionError) as e:
            raise _409(e) from e


# ------------------------------------------------------------------ sources & policy review
@router.get("/sources")
def sources(user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute(
            """select s.*, (select count(*) from source_snapshots ss where ss.source_id=s.id) as snapshots,
                      (select max(ss.last_seen_at) from source_snapshots ss where ss.source_id=s.id) as last_seen_at,
                      (select count(*) from ops_tasks t join policy_records pr on pr.id=t.policy_record_id
                         join source_snapshots ss on ss.id=pr.source_snapshot_id
                       where ss.source_id=s.id and t.status='open') as open_reviews
               from sources s order by s.country nulls last, s.topic""").fetchall()


@router.get("/sources/{source_id}")
def source_detail(source_id: str, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        snaps = conn.execute("""select id, fetched_at, last_seen_at, content_hash, changed_from_previous, provider, http_status,
                                       content_markdown from source_snapshots where source_id=%s order by fetched_at desc limit 2""",
                             (source_id,)).fetchall()
        recs = conn.execute("""select pr.*, ss.fetched_at from policy_records pr join source_snapshots ss on ss.id=pr.source_snapshot_id
                               where ss.source_id=%s order by pr.field, pr.created_at desc""", (source_id,)).fetchall()
        reviews = conn.execute("""select t.* from ops_tasks t join policy_records pr on pr.id=t.policy_record_id
                                  join source_snapshots ss on ss.id=pr.source_snapshot_id where ss.source_id=%s and t.status='open'""",
                               (source_id,)).fetchall()
        return {"source": conn.execute("select * from sources where id=%s", (source_id,)).fetchone(),
                "latest": snaps[0] if snaps else None, "previous": snaps[1] if len(snaps) > 1 else None,
                "policy_records": recs, "reviews": reviews}


class PolicyDecision(BaseModel):
    decision: Literal["verify", "dispute"]
    note: str | None = None


@router.post("/policy/{record_id}")
def decide_policy(record_id: str, body: PolicyDecision, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        status = "verified" if body.decision == "verify" else "disputed"
        r = conn.execute("update policy_records set status=%s, verified_by=%s, verified_at=now() where id=%s returning *",
                         (status, user.id, record_id)).fetchone()
        if r is None:
            raise HTTPException(404, "not found")
        conn.execute("update ops_tasks set status='done', resolved_by=%s, resolved_at=now() where policy_record_id=%s and status='open'",
                     (user.id, record_id))
        audit(conn, user.id, user.role, f"policy_{body.decision}", "policy_record", record_id, {"note": body.note})
        return r


class SourceIn(BaseModel):
    url: str
    title: str
    country: str | None = Field(default=None, max_length=2)
    topic: str
    visa_type: str | None = None
    crawl_method: Literal["firecrawl", "apify"] = "firecrawl"
    crawl_frequency_days: int = Field(default=1, ge=1, le=30)


@router.post("/sources")
def add_source(body: SourceIn, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        domains = [r["domain"] for r in conn.execute("select domain from allowed_domains")]
        if not domain_allowed(body.url, domains):
            raise HTTPException(422, "domain is not on the official allow-list (admins can extend it)")
        s = conn.execute("""insert into sources (url, title, authority, country, topic, visa_type, crawl_method, crawl_frequency)
                            values (%s,%s,%s,%s,%s,%s,%s,make_interval(days => %s)) returning *""",
                         (body.url, body.title, body.url.split("/")[2], body.country, body.topic, body.visa_type,
                          body.crawl_method, body.crawl_frequency_days)).fetchone()
        jobs.enqueue("crawl_source", {"source_id": str(s["id"])}, conn=conn)
        audit(conn, user.id, user.role, "add_source", "source", str(s["id"]))
        return s


class DomainIn(BaseModel):
    domain: str = Field(pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$")
    authority: str


@router.post("/allowed-domains")
def add_domain(body: DomainIn, user: User = Depends(admin_user)) -> dict[str, str]:
    with tx() as conn:
        conn.execute("insert into allowed_domains (domain, authority) values (%s,%s) on conflict do nothing", (body.domain, body.authority))
        audit(conn, user.id, user.role, "allow_domain", "allowed_domain", None, body.model_dump())
    return {"ok": "added"}


@router.post("/sources/{source_id}/crawl")
def crawl_now(source_id: str, user: User = Depends(staff_user)) -> dict[str, str]:
    return {"job_id": jobs.enqueue("crawl_source", {"source_id": source_id})}


# ------------------------------------------------------------------ partners & inventory
class PartnerIn(BaseModel):
    name: str
    kind: Literal["umrah_operator", "travel_agency", "consolidator"]
    licence_number: str
    licence_authority: str
    licence_expiry: date


@router.get("/partners")
def partners(user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute("""select p.*, (select count(*) from umrah_inventory u where u.partner_id=p.id and u.active) inventory
                               from partners p order by p.name""").fetchall()


@router.post("/partners")
def add_partner(body: PartnerIn, user: User = Depends(admin_user)) -> dict[str, Any]:
    with tx() as conn:
        p = conn.execute("""insert into partners (name, kind, licence_number, licence_authority, licence_expiry)
                            values (%s,%s,%s,%s,%s) returning *""",
                         (body.name, body.kind, body.licence_number, body.licence_authority, body.licence_expiry)).fetchone()
        audit(conn, user.id, user.role, "add_partner", "partner", str(p["id"]))
        return p


class InventoryIn(BaseModel):
    partner_id: str
    kind: Literal["visa", "hotel_makkah", "hotel_madinah", "transport", "ziyarat", "insurance", "flight"]
    name: str
    details: dict[str, Any] = Field(default_factory=dict)
    unit_amount_minor: int = Field(ge=0)
    currency: str = "PKR"
    per: Literal["person", "room_night", "person_night", "booking"]
    valid_from: date
    valid_to: date


@router.get("/inventory")
def inventory(partner_id: str | None = None, user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    with tx() as conn:
        return conn.execute("select * from umrah_inventory where (%s::uuid is null or partner_id=%s) order by kind, unit_amount_minor",
                            (partner_id, partner_id)).fetchall()


@router.post("/inventory")
def add_inventory(body: InventoryIn, user: User = Depends(staff_user)) -> dict[str, Any]:
    with tx() as conn:
        r = conn.execute("""insert into umrah_inventory (partner_id, kind, name, details, unit_amount_minor, currency, per, valid_from, valid_to)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
                         (body.partner_id, body.kind, body.name, Jsonb(body.details), body.unit_amount_minor, body.currency,
                          body.per, body.valid_from, body.valid_to)).fetchone()
        audit(conn, user.id, user.role, "add_inventory", "umrah_inventory", str(r["id"]))
        return r


@router.get("/usage")
def usage(user: User = Depends(staff_user)) -> list[dict[str, Any]]:
    """LLM cost dashboard: tokens per case and model."""
    with tx() as conn:
        return conn.execute("""select case_id, model, count(*) calls, sum(input_tokens) input_tokens, sum(output_tokens) output_tokens
                               from llm_usage group by case_id, model order by sum(output_tokens) desc limit 200""").fetchall()


class FxIn(BaseModel):
    currency: str
    rate_to_pkr: float = Field(gt=0)
    source: str


@router.post("/fx")
def set_fx(body: FxIn, user: User = Depends(admin_user)) -> dict[str, str]:
    with tx() as conn:
        conn.execute("""insert into fx_rates (currency, rate_to_pkr, source, updated_at) values (%s,%s,%s,now())
                        on conflict (currency) do update set rate_to_pkr=excluded.rate_to_pkr, source=excluded.source, updated_at=now()""",
                     (body.currency, body.rate_to_pkr, body.source))
        audit(conn, user.id, user.role, "set_fx", "fx_rates", None, body.model_dump())
    return {"ok": "saved"}
