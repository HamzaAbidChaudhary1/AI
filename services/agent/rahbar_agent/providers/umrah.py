"""UmrahPartnerAdapter (docs/FULFILMENT.md). MVP: ManualPartnerAdapter — ops enter partner inventory,
confirmations, visa status and vouchers in the ops console."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from ..db import Jsonb, tx


class UmrahPartnerAdapter(Protocol):
    def get_inventory(self, start: date, end: date, pax: int) -> list[dict[str, Any]]: ...
    def create_booking(self, package: dict[str, Any], travellers: list[dict[str, Any]]) -> dict[str, Any]: ...
    def get_status(self, ref: str) -> dict[str, Any]: ...


class ManualPartnerAdapter:
    """Inventory = active rows in umrah_inventory entered by ops; bookings become ops tasks."""

    def get_inventory(self, start: date, end: date, pax: int) -> list[dict[str, Any]]:
        with tx() as conn:
            return conn.execute(
                """select ui.*, p.name as partner_name, p.licence_number, p.licence_authority
                   from umrah_inventory ui join partners p on p.id = ui.partner_id
                   where ui.active and p.active and ui.valid_from <= %s and ui.valid_to >= %s
                   order by ui.kind, ui.unit_amount_minor""",
                (start, end),
            ).fetchall()

    def create_booking(self, package: dict[str, Any], travellers: list[dict[str, Any]]) -> dict[str, Any]:
        with tx() as conn:
            t = conn.execute(
                "insert into ops_tasks (kind, case_id, payload) values ('partner_booking', %s, %s) returning id",
                (package["case_id"], Jsonb({"package": package, "traveller_count": len(travellers)})),
            ).fetchone()
        return {"status": "requested", "ops_task_id": str(t["id"])}

    def get_status(self, ref: str) -> dict[str, Any]:
        with tx() as conn:
            b = conn.execute("select status, provider_ref from bookings where provider_ref=%s", (ref,)).fetchone()
        return b or {"status": "unknown"}
