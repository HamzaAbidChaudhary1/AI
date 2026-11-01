# UI & Internationalisation

## Languages
- `en` and `ur`, toggle in header, persisted to `profiles.preferred_locale` and cookie.
- next-intl with message files `messages/en.json`, `messages/ur.json`. No hard-coded strings.
- Urdu: `dir="rtl"` on `<html>`, font **Noto Nastaliq Urdu** (Google Fonts) for Urdu text, line-height ≥ 2 for Nastaliq. Use Tailwind logical properties (`ms-`, `me-`, `ps-`, `pe-`) so layouts flip correctly.
- Numbers, dates and currency: format with `Intl` for the locale; always show currency code (PKR, SAR, USD).
- Input accepts English, Urdu and **Roman Urdu** in any locale; the agent replies in the selected locale.
- Official terms in Urdu UI keep the English term in brackets, e.g. "مالی ثبوت (Proof of funds)".

## Customer screens
1. **Landing:** "The honest travel agency" message, services, how transparency works, Scam Checker CTA.
2. **Chat (`/chat`):** main agent surface.
   - Streaming progress steps rendered as a checklist that ticks as the agent works.
   - Citations as small source chips with "verified <date>".
   - Rich cards: Assessment (strength badge + reasons), Quote (itemised table with payee column), Document checklist, Flight options, Hotel options, Umrah package comparison, **Confirm action** card (explicit "Yes, submit/book/pay" button with summary).
   - Long jobs show "Working on it — we'll notify you" with ETA.
3. **Scam Checker (`/scam-check`):** no login; textarea + file upload; result with red flags, official facts with sources, verification steps, CTA.
4. **Visa destination pages (`/visa/[country]`):** requirements, fees (cited, last verified), timelines, "Start application".
5. **Umrah (`/umrah`):** package builder form → options comparison.
6. **Flights / Hotels:** search → results → itemised checkout.
7. **Cases (`/cases`, `/cases/[id]`):** status stepper, live timeline (`case_events` via Realtime), documents with review findings, quote/invoice, bookings with real reference numbers and downloadable tickets/vouchers, refund policy.
8. **Account:** travellers (manage family members), language, notifications.

## Ops console (`/ops`, en only)
- Case queue with filters (status, service, SLA breach).
- Case detail: AI assessment, documents viewer, review findings, application pack with copy-field UI, actions (approve/submit/enter reference/issue/refund), internal notes (not user-visible).
- Sources & policy review (see CRAWLING.md).
- Partners management.

## Design principles
- Trust first: calm, plain, no countdown timers or pressure tactics.
- Every price is a table, never a single number.
- Elderly-friendly: large tap targets, readable font sizes (≥ 16px body, ≥ 18px Urdu), high contrast.
- Mobile-first web (most users on phones).
