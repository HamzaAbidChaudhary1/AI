"""Money: integer minor units + ISO currency code. Never floats for stored amounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

CURRENCIES = {"PKR", "USD", "SAR", "EUR", "GBP", "AED", "TRY", "MYR"}
MINOR_DIGITS = dict.fromkeys(CURRENCIES, 2)


class Money(BaseModel):
    amount_minor: int = Field(ge=0)
    currency: str

    def model_post_init(self, _: object) -> None:
        if self.currency not in CURRENCIES:
            raise ValueError(f"unsupported currency {self.currency}")


def convert_minor(amount_minor: int, from_ccy: str, to_ccy: str, fx_rates: dict[str, str | float]) -> int:
    """fx_rates maps currency -> value of 1 unit in the quote currency (`to_ccy`),
    e.g. for a PKR quote {"GBP": "356.20", "USD": "280.50"}. Rounds half-up to the minor unit."""
    if from_ccy == to_ccy:
        return amount_minor
    if from_ccy not in fx_rates:
        raise ValueError(f"missing FX rate {from_ccy}->{to_ccy}")
    rate = Decimal(str(fx_rates[from_ccy]))
    if rate <= 0:
        raise ValueError("FX rate must be positive")
    src = Decimal(amount_minor) / (10 ** MINOR_DIGITS[from_ccy])
    dst = (src * rate * (10 ** MINOR_DIGITS[to_ccy])).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(dst)


def format_money(amount_minor: int, currency: str, locale: str = "en") -> str:
    """Always shows the currency code (UI_I18N.md)."""
    value = Decimal(amount_minor) / (10 ** MINOR_DIGITS.get(currency, 2))
    digits = 0 if value == value.to_integral() else 2
    text = f"{value:,.{digits}f}"
    return f"{currency} {text}"
