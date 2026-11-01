"""FlightProvider adapter (docs/FULFILMENT.md). Sandbox first: deterministic fake offers."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, Field

AIRPORTS_PK = {"LHE", "KHI", "ISB", "MUX", "SKT", "PEW"}


class FlightSearch(BaseModel):
    origin: str
    destination: str
    depart_date: date
    return_date: date | None = None
    adults: int = Field(default=1, ge=1, le=9)
    cabin: str = "economy"


class FlightOffer(BaseModel):
    offer_id: str
    airline: str
    flight_numbers: list[str]
    origin: str
    destination: str
    depart_at: datetime
    arrive_at: datetime
    return_depart_at: datetime | None = None
    stops: int
    fare_minor: int          # base fare, all passengers
    taxes_minor: int
    currency: str
    baggage: str
    refundable: bool
    fare_rules_en: str
    fare_rules_ur: str
    expires_at: datetime
    provider: str = "sandbox"


class Pax(BaseModel):
    full_name_as_passport: str
    date_of_birth: date | None = None
    passport_last4: str | None = None


class Hold(BaseModel):
    hold_id: str
    pnr: str
    offer_id: str
    expires_at: datetime


class Ticket(BaseModel):
    pnr: str
    ticket_numbers: list[str]
    e_ticket_url: str | None = None


class BookingStatus(BaseModel):
    booking_ref: str
    status: str


class FlightProvider(Protocol):
    name: str

    def search(self, req: FlightSearch) -> list[FlightOffer]: ...
    def hold(self, offer_id: str, passengers: list[Pax]) -> Hold: ...
    def issue(self, hold_id: str, payment_ref: str) -> Ticket: ...
    def get(self, booking_ref: str) -> BookingStatus: ...


_AIRLINES = [("PIA", "PK", 0, 1.00), ("Emirates", "EK", 1, 1.25), ("Saudia", "SV", 0, 1.10),
             ("Qatar Airways", "QR", 1, 1.30), ("flydubai", "FZ", 1, 0.80), ("Air Arabia", "G9", 1, 0.75),
             ("Serene Air", "ER", 0, 0.90), ("AirSial", "PF", 0, 0.85)]


def _h(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


class SandboxFlightProvider:
    """Fake but stable data so flows and UI can be built. Never shown as real fares (offers say provider=sandbox)."""

    name = "sandbox"
    _holds: dict[str, Hold] = {}
    _status: dict[str, str] = {}

    def search(self, req: FlightSearch) -> list[FlightOffer]:
        base = 6_000_000 if req.destination in {"LHR", "MAN", "FRA", "IST"} else 2_500_000  # PKR minor, per adult
        out: list[FlightOffer] = []
        for name, code, stops, mult in _AIRLINES[:5]:
            seed = int(_h(req.model_dump_json(), code)[:6], 16)
            depart = datetime.combine(req.depart_date, datetime.min.time(), UTC) + timedelta(hours=2 + seed % 18)
            dur = timedelta(hours=4 + stops * 3 + seed % 3)
            fare = int(base * mult) * req.adults
            out.append(FlightOffer(
                offer_id="sbx_" + _h(req.model_dump_json(), code)[:16], airline=name,
                flight_numbers=[f"{code}{100 + seed % 800}"] + ([f"{code}{900 - seed % 300}"] if stops else []),
                origin=req.origin, destination=req.destination, depart_at=depart, arrive_at=depart + dur,
                return_depart_at=(datetime.combine(req.return_date, datetime.min.time(), UTC) + timedelta(hours=10))
                if req.return_date else None,
                stops=stops, fare_minor=fare, taxes_minor=int(fare * 0.18), currency="PKR",
                baggage="30 kg checked + 7 kg cabin" if code in ("PK", "SV", "EK", "QR") else "20 kg checked + 7 kg cabin",
                refundable=code in ("EK", "QR"),
                fare_rules_en="Refundable with a penalty before departure." if code in ("EK", "QR")
                else "Non-refundable. Date change allowed for a fee.",
                fare_rules_ur="روانگی سے پہلے جرمانے کے ساتھ قابلِ واپسی۔" if code in ("EK", "QR")
                else "ناقابلِ واپسی۔ فیس کے ساتھ تاریخ تبدیل ہو سکتی ہے۔",
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            ))
        return sorted(out, key=lambda o: o.fare_minor + o.taxes_minor)

    def hold(self, offer_id: str, passengers: list[Pax]) -> Hold:
        pnr = _h(offer_id, len(passengers)).upper()[:6]
        h = Hold(hold_id="hold_" + pnr, pnr=pnr, offer_id=offer_id, expires_at=datetime.now(UTC) + timedelta(hours=24))
        self._holds[h.hold_id] = h
        self._status[pnr] = "held"
        return h

    def issue(self, hold_id: str, payment_ref: str) -> Ticket:
        h = self._holds.get(hold_id)
        if h is None:
            raise ValueError("unknown hold")
        self._status[h.pnr] = "ticketed"
        return Ticket(pnr=h.pnr, ticket_numbers=["214" + _h(h.pnr, payment_ref)[:10].upper()])

    def get(self, booking_ref: str) -> BookingStatus:
        return BookingStatus(booking_ref=booking_ref, status=self._status.get(booking_ref, "unknown"))


def get_flight_provider() -> FlightProvider:
    from ..config import get_settings

    name = get_settings().flight_provider
    if name == "sandbox":
        return SandboxFlightProvider()
    raise NotImplementedError(f"flight provider {name} not configured yet (Phase 6)")
