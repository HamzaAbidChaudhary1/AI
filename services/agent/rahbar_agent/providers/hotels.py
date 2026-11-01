"""HotelProvider adapter (docs/FULFILMENT.md). Sandbox first."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, Field


class HotelSearch(BaseModel):
    city: str
    check_in: date
    check_out: date
    guests: int = Field(default=2, ge=1, le=12)
    rooms: int = Field(default=1, ge=1, le=6)


class HotelOffer(BaseModel):
    offer_id: str
    name: str
    city: str
    stars: int
    room: str
    board: str
    nights: int
    total_minor: int
    currency: str
    cancellation_en: str
    cancellation_ur: str
    distance_note: str | None = None
    expires_at: datetime
    provider: str = "sandbox"


class Guest(BaseModel):
    full_name_as_passport: str


class HotelBooking(BaseModel):
    booking_ref: str
    status: str
    voucher_url: str | None = None


class CancelResult(BaseModel):
    booking_ref: str
    cancelled: bool
    penalty_minor: int = 0


class HotelProvider(Protocol):
    name: str

    def search(self, req: HotelSearch) -> list[HotelOffer]: ...
    def book(self, offer_id: str, guests: list[Guest], payment_ref: str) -> HotelBooking: ...
    def cancel(self, booking_ref: str) -> CancelResult: ...


class SandboxHotelProvider:
    name = "sandbox"

    def search(self, req: HotelSearch) -> list[HotelOffer]:
        nights = (req.check_out - req.check_in).days
        if nights <= 0:
            raise ValueError("check_out must be after check_in")
        out = []
        for i, (stars, rate) in enumerate([(3, 1_200_000), (4, 2_200_000), (5, 4_000_000)]):
            oid = "sbxh_" + hashlib.sha256(f"{req.model_dump_json()}{i}".encode()).hexdigest()[:14]
            out.append(HotelOffer(
                offer_id=oid, name=f"Sandbox {req.city} Hotel {'★' * stars}", city=req.city, stars=stars,
                room="Double room" if req.guests <= 2 else "Family room", board="Breakfast included" if stars > 3 else "Room only",
                nights=nights, total_minor=rate * nights * req.rooms, currency="PKR",
                cancellation_en="Free cancellation until 72 hours before check-in; after that the first night is charged.",
                cancellation_ur="چیک اِن سے 72 گھنٹے پہلے تک مفت منسوخی؛ اس کے بعد پہلی رات کا کرایہ لیا جائے گا۔",
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            ))
        return out

    def book(self, offer_id: str, guests: list[Guest], payment_ref: str) -> HotelBooking:
        return HotelBooking(booking_ref="HTL-" + hashlib.sha256(offer_id.encode()).hexdigest()[:8].upper(), status="confirmed")

    def cancel(self, booking_ref: str) -> CancelResult:
        return CancelResult(booking_ref=booking_ref, cancelled=True)


def get_hotel_provider() -> HotelProvider:
    from ..config import get_settings

    if get_settings().hotel_provider == "sandbox":
        return SandboxHotelProvider()
    raise NotImplementedError("hotel provider not configured yet (Phase 6)")
