# PRD — Rahbar MVP

## Problem

Pakistani students, workers, families and pilgrims routinely lose lakhs of rupees (often tens of thousands of dollars) to fake visa consultants and travel agents who promise "guaranteed" visas, charge inflated or fake fees, forge documents, and disappear. FIA arrests happen every month, yet the pattern continues because people have no trustworthy, affordable alternative and no way to verify what they're told. The human cost includes ruined finances, refusals on record, and in some cases suicide.

## Positioning

**"The honest travel agency."** We cannot get anyone a visa; embassies decide. We give the truth about your chances, the real costs, and do all the work of applying and booking with every step, fee and reference number visible to you.

## Users

1. **Visitor / family traveller:** tourist or family visit visas (UAE, Türkiye, Schengen, UK, Malaysia, Thailand, etc.)
2. **Umrah pilgrim:** often older, less tech-comfortable, frequently booked by a family member. Needs packages (visa + flights + hotels + transport).
3. **Student** *(roadmap, not MVP)*
4. **Worker** *(roadmap, needs OEP licence)*
5. **Ops staff (internal):** review AI-prepared cases, submit to portals, issue tickets, handle exceptions.

## MVP services

| Service | MVP? | Notes |
|---|---|---|
| Consultation & eligibility assessment | ✅ | Deep reasoning agent |
| Visit / tourist visas (5–6 destinations) | ✅ | Start: UAE, Türkiye, Schengen (pick 1–2 countries), UK visitor, Malaysia, Saudi tourist |
| Umrah packages | ✅ | Fulfilled with licensed partner operator |
| Flight booking | ✅ | Via provider adapter / partner consolidator |
| Hotel booking | ✅ | Via provider adapter; Makkah/Madinah via Umrah partner |
| Tour / itinerary planning | ✅ | Agent generates itinerary; bookable items link to bookings |
| Scam Checker | ✅ | Free, no login required |
| Student visas | ❌ | Roadmap |
| Work visas | ❌ | Roadmap (requires OEP licence) |
| WhatsApp / voice | ❌ | Explicitly out of scope |

## Core journeys

### J1. Visit visa application
1. User picks destination + purpose + dates (or describes trip in chat).
2. Agent runs **eligibility assessment**: asks for profile (employment, income, travel history, prior refusals, sponsor, ties to Pakistan). Produces: requirements list (cited), honest strength rating (Strong / Fair / Weak) with reasons, what would strengthen it, realistic timeline.
3. **Itemised quote** generated (gov fee, VFS fee, our service fee, optional flight/hotel/insurance).
4. User accepts → **Case** created → document checklist.
5. User uploads documents → **AI document review** flags issues (name mismatches across passport/CNIC/bank statement, insufficient balance vs. requirement, unexplained large deposits, expired passport, missing pages).
6. Agent prepares **application pack**: pre-filled form data, cover letter, itinerary, document index.
7. User reviews and confirms → ops/partner submits → **reference number** shown to user.
8. Biometrics appointment booked (by ops or user, guided). Status tracked until decision.
9. On refusal: agent explains the refusal reasons honestly and whether reapplying makes sense.

### J2. Umrah package
1. User enters travellers, dates, departure city, budget, hotel distance preference, Makkah/Madinah nights split.
2. Agent builds 2–3 **transparent package options**: each line item (visa, flight, hotel Makkah, hotel Madinah, transport, ziyarat, insurance, service fee) with source/provider.
3. User selects → travellers' documents collected → partner processes visa → flights & hotels booked → vouchers/tickets delivered in-app.

### J3. Flight / hotel only
Search → itemised price including our fee → confirm → pay → booking reference + e-ticket/voucher.

### J4. Scam Checker (no login)
User pastes or uploads what an agent offered (text, offer letter, receipt, screenshot). Agent returns: red flags found, what official fees actually are (cited), whether claims like "guaranteed visa" or "job visa without OEP" are possible, how to verify the agent (BEOE licence list, FIA complaint channels), and a CTA to do it properly with us.

## Transparency features (must ship in MVP)

- Itemised quotes and invoices; our fee always a separate, visible line.
- Every policy statement shows source link + "last verified" date.
- Case timeline (`case_events`) visible to user: every action, who did it (AI / ops / partner), when.
- Real reference numbers (visa application ref, PNR, hotel confirmation).
- Published refund policy per service, enforced by system rules.
- Strength rating with reasons shown before payment.

## Success metrics (MVP)

- Quote → paid conversion rate
- Cases completed end-to-end
- Visa approval rate on submitted cases (and refusal reasons)
- Time from case creation to submission
- Scam Checker uses → signups
- NPS / referral rate

## Out of scope for MVP

WhatsApp, voice, native mobile apps, vector RAG (crawling only for now; RAG is a future phase), student & work visas, multi-currency card payments abroad.
