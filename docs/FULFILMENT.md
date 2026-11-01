# Fulfilment — how we actually apply and book

The AI does the agency work end to end; regulated or irreversible steps are executed through ops staff and licensed partners in the MVP, then progressively automated once we hold our own licences.

## Operating model (MVP)

| Step | Who executes | Why |
|---|---|---|
| Consultation, assessment, quote, doc collection & review, application pack | AI | core product |
| Visa submission on government/VFS/e-visa portals | Ops staff (or partner) using the AI-prepared pack | most portals have no API, use CAPTCHAs, and require applicant declarations; we don't automate around these |
| Biometrics / appointment booking | Ops or user (guided) | applicant must attend in person |
| Umrah visa + Makkah/Madinah hotels + transport | Licensed Umrah partner operator | Umrah operator registration required |
| Flight ticket issuance | Provider API or partner consolidator under their licence/IATA | licensing |
| Hotel booking (non-Umrah) | Hotel provider API | |
| Payments | Gateway / bank transfer, itemised ledger | |

As we get licences (travel agency, Umrah operator, later OEP), partner steps move in-house. Code must not care: everything goes through adapters + the ops console.

## Visa application flow

1. Case reaches `pack_ready` after document review passes.
2. Pack contents (generated):
   - `form_data.json` mapped to the target portal's fields (one mapper per destination, `services/agent/forms/<country>.py`)
   - cover letter (en), travel itinerary, document index with filenames
   - checklist of what the applicant must bring to biometrics
3. User reviews pack in app → confirms declarations themselves (checkbox per declaration, logged).
4. Case → `awaiting_user_confirmation` → user confirms → ops task created.
5. Ops console shows pack side-by-side with a "copy field" UI for fast manual portal entry. Ops enters the portal reference number → `submitted`, event shown to user.
6. Worker reminders for biometrics; ops updates status as decisions arrive (or user reports decision / uploads passport stamp or e-visa).
7. Refusal → agent `refusal_analysis` explains reasons and next steps honestly.

Future: assisted browser automation for specific e-visa portals where allowed by terms; never bypass CAPTCHAs.

## Flights

Adapter interface:
```python
class FlightProvider(Protocol):
    def search(self, req: FlightSearch) -> list[FlightOffer]: ...
    def hold(self, offer_id: str, passengers: list[Pax]) -> Hold: ...
    def issue(self, hold_id: str, payment_ref: str) -> Ticket: ...
    def get(self, booking_ref: str) -> BookingStatus: ...
```
- Implement `SandboxFlightProvider` first (fake data) for UI and flows.
- Candidates: Duffel API, or a Pakistani consolidator/partner agency with GDS access (verify route coverage for PIA, Saudia, Emirates, Qatar, Flydubai, Air Arabia, Serene, AirSial from LHE/KHI/ISB/MUX/SKT/PEW).
- Always show fare + taxes + our service fee as separate lines.
- Issue only after payment `verified` + user confirm + ops approve (MVP).

## Hotels

```python
class HotelProvider(Protocol):
    def search(self, req: HotelSearch) -> list[HotelOffer]: ...
    def book(self, offer_id: str, guests: list[Guest], payment_ref: str) -> HotelBooking: ...
    def cancel(self, booking_ref: str) -> CancelResult: ...
```
- Sandbox first; real provider TBD (bedbank API such as Hotelbeds/RateHawk, or partner).
- Show cancellation policy clearly in both languages before confirm.
- Makkah/Madinah: via Umrah partner inventory; show walking distance to Haram as provided by partner, labelled as such.

## Umrah packages

- `UmrahPartnerAdapter`: `get_inventory(dates, pax)`, `create_booking(package, travellers)`, `get_status(ref)`.
- MVP partner integration may be manual: ops console form where ops enters partner's confirmation, visa status and vouchers. Build the adapter interface anyway with a `ManualPartnerAdapter`.
- Package builder agent outputs 2–3 options; every line item has a payee and price source.
- Collect per traveller: passport scan, photo, CNIC, vaccination certificates if required (check current Saudi requirements via crawled sources).

## Tour / itinerary plans

- Agent generates day-by-day itinerary (JSON + rendered PDF). Bookable items (flights, hotels) link to booking flow; non-bookable items are suggestions with no price promises.

## Payments & money transparency

- `PaymentProvider` adapter; start with `ManualBankTransfer` (user uploads receipt, ops verifies).
- Ledger is per quote line item and records the **payee** (government, VFS, airline, hotel, partner, Rahbar).
- Where possible, government/VFS fees are paid by the applicant directly on the official portal; then that line is marked `paid_directly_by_user` and excluded from our collection.
- Refund rules per service in `refund_policies` config; refunds triggered from ops console with reason, logged to `case_events`.
- Our service fee is fixed per service from a config table, shown before any document upload.
