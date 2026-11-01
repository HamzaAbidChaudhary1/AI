"""PaymentProvider adapter. MVP: ManualBankTransfer (user uploads receipt, ops verifies).
No card data ever touches our servers (gateway-hosted checkout in Phase 6)."""

from __future__ import annotations

from typing import Any, Protocol


class PaymentProvider(Protocol):
    name: str

    def create_payment_request(self, quote: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...


class ManualBankTransfer:
    name = "manual_bank_transfer"

    def __init__(self, account_title: str = "Rahbar (Pvt) Ltd — CLIENT FUNDS (placeholder)",
                 iban: str = "PK00 XXXX 0000 0000 0000 0000 (placeholder)", bank: str = "To be configured") -> None:
        self.account_title, self.iban, self.bank = account_title, iban, bank

    def create_payment_request(self, quote: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        ref = "RB-" + idempotency_key[:8].upper()
        return {
            "provider": self.name, "reference": ref, "amount_minor": quote["collect_minor"], "currency": quote["currency"],
            "instructions": {"account_title": self.account_title, "iban": self.iban, "bank": self.bank,
                             "payment_reference": ref},
        }


def get_payment_provider() -> PaymentProvider:
    from ..config import get_settings

    if get_settings().payment_provider == "manual":
        return ManualBankTransfer()
    raise NotImplementedError("payment gateway not configured yet (Phase 6)")
