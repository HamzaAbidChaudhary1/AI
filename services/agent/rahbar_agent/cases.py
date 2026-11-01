"""Case lifecycle + user-visible audit timeline (case_events). CLAUDE.md rule 5: every action logged."""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from .db import Jsonb
from .i18n import event_text

# allowed transitions; anything else is a bug and is refused
TRANSITIONS: dict[str, set[str]] = {
    "consulting": {"assessed", "quoted", "cancelled"},
    "assessed": {"quoted", "consulting", "cancelled"},
    "quoted": {"accepted", "quoted", "assessed", "cancelled"},
    "accepted": {"collecting_documents", "booked", "cancelled", "refunded"},
    # umrah packages go straight to booked once the partner confirms (no visa pack step on our side)
    "collecting_documents": {"documents_review", "booked", "cancelled", "refunded"},
    "documents_review": {"collecting_documents", "pack_ready", "booked", "cancelled", "refunded"},
    "pack_ready": {"awaiting_user_confirmation", "collecting_documents", "cancelled", "refunded"},
    "awaiting_user_confirmation": {"submitted", "pack_ready", "booked", "cancelled", "refunded"},
    "submitted": {"biometrics_scheduled", "in_process", "decision_approved", "decision_refused"},
    "biometrics_scheduled": {"in_process", "decision_approved", "decision_refused"},
    "in_process": {"decision_approved", "decision_refused"},
    "decision_approved": {"booked", "completed"},
    "decision_refused": {"completed", "consulting"},
    "booked": {"completed", "refunded", "cancelled"},
    "completed": set(),
    "cancelled": {"refunded"},
    "refunded": set(),
}

ACTORS = {"ai", "ops", "partner", "user", "system"}


class TransitionError(ValueError):
    pass


def add_event(conn: Connection, case_id: str, actor_type: str, event_type: str, *, actor_id: str | None = None,
              data: dict[str, Any] | None = None, visible: bool = True, **fmt: Any) -> dict[str, Any]:
    if actor_type not in ACTORS:
        raise ValueError(actor_type)
    en, ur = event_text(event_type, **fmt)
    return conn.execute(
        """insert into case_events (case_id, actor_type, actor_id, event_type, message_en, message_ur, data, visible_to_user)
           values (%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
        (case_id, actor_type, actor_id, event_type, en, ur, Jsonb(data or {}), visible),
    ).fetchone()


def create_case(conn: Connection, owner_id: str, service_type: str, *, destination: str | None = None,
                purpose: str | None = None, trip: dict[str, Any] | None = None,
                traveller_ids: list[str] | None = None) -> dict[str, Any]:
    case = conn.execute(
        """insert into cases (owner_id, service_type, destination_country, purpose, trip)
           values (%s,%s,%s,%s,%s) returning *""",
        (owner_id, service_type, destination, purpose, Jsonb(trip or {})),
    ).fetchone()
    for tid in traveller_ids or []:
        conn.execute("insert into case_travellers (case_id, traveller_id) values (%s,%s) on conflict do nothing",
                     (case["id"], tid))
    add_event(conn, case["id"], "ai", "case_created", service=service_type)
    return case


def transition(conn: Connection, case_id: str, to: str, *, actor_type: str, actor_id: str | None = None,
               event: str | None = None, data: dict[str, Any] | None = None, visible: bool = True,
               **fmt: Any) -> dict[str, Any]:
    row = conn.execute("select status from cases where id=%s for update", (case_id,)).fetchone()
    if row is None:
        raise TransitionError("unknown case")
    frm = row["status"]
    if to != frm and to not in TRANSITIONS[frm]:
        raise TransitionError(f"cannot move case from {frm} to {to}")
    conn.execute(
        "update cases set status=%s, completed_at = case when %s in ('completed','refunded') then now() else completed_at end where id=%s",
        (to, to, case_id),
    )
    add_event(conn, case_id, actor_type, event or "status_changed", actor_id=actor_id,
              data={**(data or {}), "from": frm, "to": to}, visible=visible, **({"status": to} | fmt))
    return conn.execute("select * from cases where id=%s", (case_id,)).fetchone()
