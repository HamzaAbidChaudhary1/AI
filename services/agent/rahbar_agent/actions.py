"""Irreversible-action gate (CLAUDE.md rules 5 & 7).

request -> user confirms (explicit, with declarations) -> ops approves (MVP) -> executor runs.
Executors call require_approved() and refuse to run otherwise.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from . import cases
from .db import Jsonb

IRREVERSIBLE = {"submit_visa", "issue_ticket", "book_hotel", "book_umrah", "pay_out", "refund"}


class ActionNotApproved(PermissionError):
    pass


def request_action(conn: Connection, case_id: str, kind: str, summary_en: str, summary_ur: str,
                   payload: dict[str, Any] | None = None, *, requires_ops: bool | None = None,
                   actor_type: str = "ai") -> dict[str, Any]:
    if requires_ops is None:
        requires_ops = kind in IRREVERSIBLE
    conn.execute("update pending_actions set status='cancelled' where case_id=%s and kind=%s and status in ('awaiting_user','awaiting_ops')",
                 (case_id, kind))
    row = conn.execute(
        """insert into pending_actions (case_id, kind, summary_en, summary_ur, payload, requires_ops)
           values (%s,%s,%s,%s,%s,%s) returning *""",
        (case_id, kind, summary_en, summary_ur, Jsonb(payload or {}), requires_ops),
    ).fetchone()
    cases.add_event(conn, case_id, actor_type, "awaiting_confirmation", summary=summary_en,
                    data={"action_id": str(row["id"]), "kind": kind})
    return row


def request_ops_action(conn: Connection, case_id: str, kind: str, summary_en: str, summary_ur: str,
                       payload: dict[str, Any], requested_by: str) -> dict[str, Any]:
    """Ops-initiated irreversible step (e.g. refund): four-eyes — a different ops/admin must approve."""
    row = conn.execute(
        """insert into pending_actions (case_id, kind, summary_en, summary_ur, payload, requires_ops, status)
           values (%s,%s,%s,%s,%s,true,'awaiting_ops') returning *""",
        (case_id, kind, summary_en, summary_ur, Jsonb({**payload, "ops_initiated": True, "requested_by": requested_by})),
    ).fetchone()
    conn.execute("insert into ops_tasks (kind, case_id, payload) values (%s,%s,%s)",
                 (kind, case_id, Jsonb({"action_id": str(row["id"]), "four_eyes": True})))
    cases.add_event(conn, case_id, "ops", "ops_note", actor_id=requested_by, visible=False,
                    note=f"{kind} requested: {summary_en}", data={"action_id": str(row["id"])})
    return row


def confirm_by_user(conn: Connection, action_id: str, user_id: str,
                    declarations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    a = conn.execute(
        "select pa.*, c.owner_id from pending_actions pa join cases c on c.id=pa.case_id where pa.id=%s for update",
        (action_id,)).fetchone()
    if a is None or str(a["owner_id"]) != str(user_id):
        raise ActionNotApproved("not found")
    if a["status"] != "awaiting_user":
        raise ActionNotApproved(f"action is {a['status']}")
    required = a["payload"].get("required_declarations", [])
    given = {d["code"] for d in (declarations or []) if d.get("accepted") is True}
    missing = [d["code"] for d in required if d["code"] not in given]
    if missing:
        raise ActionNotApproved(f"declarations not accepted: {', '.join(missing)}")
    status = "awaiting_ops" if a["requires_ops"] else "approved"
    conn.execute(
        """update pending_actions set status=%s, user_confirmed_by=%s, user_confirmed_at=now(), declarations=%s
           where id=%s""",
        (status, user_id, Jsonb(declarations or []), action_id),
    )
    cases.add_event(conn, a["case_id"], "user", "user_confirmed", actor_id=user_id, summary=a["summary_en"],
                    data={"action_id": action_id, "kind": a["kind"]})
    if a["requires_ops"]:
        conn.execute("insert into ops_tasks (kind, case_id, payload) values (%s,%s,%s)",
                     (a["kind"], a["case_id"], Jsonb({"action_id": action_id})))
    return conn.execute("select * from pending_actions where id=%s", (action_id,)).fetchone()


def approve_by_ops(conn: Connection, action_id: str, ops_id: str, *, approve: bool = True,
                   reason: str | None = None) -> dict[str, Any]:
    a = conn.execute("select * from pending_actions where id=%s for update", (action_id,)).fetchone()
    if a is None or a["status"] != "awaiting_ops":
        raise ActionNotApproved("action is not awaiting ops approval")
    if approve and a["payload"].get("ops_initiated") and a["payload"].get("requested_by") == str(ops_id):
        raise ActionNotApproved("four-eyes rule: a different team member must approve")
    if approve:
        conn.execute("update pending_actions set status='approved', ops_approved_by=%s, ops_approved_at=now() where id=%s",
                     (ops_id, action_id))
        cases.add_event(conn, a["case_id"], "ops", "ops_approved", actor_id=ops_id, summary=a["summary_en"],
                        data={"action_id": action_id})
    else:
        conn.execute("update pending_actions set status='rejected', result=%s where id=%s",
                     (Jsonb({"reason": reason}), action_id))
        cases.add_event(conn, a["case_id"], "ops", "ops_rejected", actor_id=ops_id, reason=reason or "-",
                        data={"action_id": action_id})
    conn.execute("update ops_tasks set status=%s, resolved_by=%s, resolved_at=now() where payload->>'action_id'=%s and status='open'",
                 ("done" if approve else "rejected", ops_id, action_id))
    return conn.execute("select * from pending_actions where id=%s", (action_id,)).fetchone()


def require_approved(conn: Connection, action_id: str | None, kind: str, case_id: str) -> dict[str, Any]:
    """Guard used by every irreversible executor."""
    if not action_id:
        raise ActionNotApproved(f"{kind} requires a confirmed and approved action")
    a = conn.execute("select * from pending_actions where id=%s for update", (action_id,)).fetchone()
    if a is None or a["kind"] != kind or str(a["case_id"]) != str(case_id):
        raise ActionNotApproved("action does not match")
    if a["status"] != "approved":
        raise ActionNotApproved(f"action is {a['status']}")
    if a["user_confirmed_at"] is None and not a["payload"].get("ops_initiated"):
        raise ActionNotApproved("user confirmation missing")
    if a["requires_ops"] and a["ops_approved_at"] is None:
        raise ActionNotApproved("ops approval missing")
    return a


def mark_executed(conn: Connection, action_id: str, result: dict[str, Any]) -> None:
    conn.execute("update pending_actions set status='executed', executed_at=now(), result=%s where id=%s",
                 (Jsonb(result), action_id))


def confirm_card(a: dict[str, Any]) -> dict[str, Any]:
    return {"type": "confirm_action", "action_id": str(a["id"]), "case_id": str(a["case_id"]), "kind": a["kind"],
            "summary_en": a["summary_en"], "summary_ur": a["summary_ur"], "status": a["status"],
            "requires_ops": a["requires_ops"], "declarations": a["payload"].get("required_declarations", [])}
