# Build Plan

Build in phases. Each phase ends with its acceptance criteria passing. Use sandbox providers until Phase 6.

## Phase 0 — Foundations
- Monorepo scaffold per CLAUDE.md layout; lint, format, CI (typecheck + tests).
- Supabase project, migrations for all tables in DATA_MODEL.md, RLS policies + tests, seed data.
- Next.js app with next-intl (en/ur), RTL switching, Nastaliq font, auth (Supabase email + phone OTP).
- FastAPI skeleton with Supabase JWT auth, health check, `jobs` worker loop.
- Railway (api + worker, own workspace) + Vercel deploys for staging.
**Accept:** user can sign up, switch to Urdu and see a correct RTL layout; worker processes a dummy job.

## Phase 1 — Crawling knowledge layer
- `sources` seed for 6 destinations + BEOE/FIA + Umrah sources.
- Firecrawl + Apify adapters, `crawl_source`, change detection, `extract_policy` with JSON schema.
- Postgres FTS over snapshots; `get_policy`, `search_snapshots`, `live_fetch` tools.
- `/ops/sources` with diff view and approve/dispute.
**Accept:** daily crawl runs; changing a fixture page creates a new snapshot, updated policy record and ops review task.

## Phase 2 — Agent core + chat
- LangGraph graph (router, quick_answer, consult, assess_eligibility, respond) with Postgres checkpointer.
- SSE streaming protocol; chat UI with progress checklist, citations, assessment card.
- Guardrail validators (no guarantees, citations required) + tests.
- Model routing via env vars.
**Accept:** asking "UK visit visa for my parents, what do they need?" in Urdu returns a cited, honest answer in Urdu with progress steps streamed; assessment produces a strength rating with reasons.

## Phase 3 — Scam Checker
- Public `/scam-check`, rate limiting, file upload (images/PDF), agent `scam_check` node, `verify_agent_licence`.
**Accept:** pasting "100% guaranteed Canada work visa, pay 15 lakh cash" yields red flags, official facts with sources and verification steps.

## Phase 4 — Cases, quotes, documents
- Case lifecycle + `case_events` timeline with Realtime.
- Itemised quote builder (service-fee config table), quote card, accept flow.
- Document checklist, upload (signed URLs), encryption of IDs, `review_documents` deep job with findings UI.
- Application pack generator for 2 destinations first (e.g. UK visitor, Türkiye e-visa).
**Accept:** full J1 flow up to `pack_ready` with an issue detected in a deliberately mismatched bank statement.

## Phase 5 — Ops console & fulfilment (manual partner mode)
- Ops queue, case detail, pack copy-field UI, confirm/approve interrupts wired to LangGraph, reference entry, refunds.
- `ManualPartnerAdapter` for Umrah; `ManualBankTransfer` payments with receipt verification.
- Umrah package builder (J2) using partner inventory entered by ops.
**Accept:** a visit-visa case goes from chat → submitted with reference number visible to the user; an Umrah package is quoted, paid (manual) and booked with vouchers delivered in-app.

## Phase 6 — Real providers
- Flight provider (Duffel or partner consolidator) behind adapter; hotel provider; payment gateway (Safepay/PayFast/JazzCash/Easypaisa).
- Webhooks, idempotency, status polling jobs.
**Accept:** real flight search → hold → pay → issue in provider test mode; hotel booking + cancellation in test mode.

## Phase 7 — Hardening for launch
- Sentry with PII redaction, audit log, data export/delete, retention job.
- ToS/Privacy (en/ur), refund policies page, "How we're different" transparency page.
- Load test chat + streaming; cost dashboard for LLM usage per case.
**Accept:** security checklist in SECURITY.md fully ticked; staging pilot with 10–20 real users.

## Later (post-investment)
Curated RAG knowledge base · own travel-agency & Umrah licences (move partner steps in-house) · student visas via university partnerships · work visas after OEP licence · licensed adviser marketplace (UK/Canada/Australia) · mobile apps.
