# CLAUDE.md — Rahbar (working name)

> Rahbar (رہبر, "guide") is a placeholder name. Replace it everywhere once the brand is final.

## What we are building

An AI-run travel and visa agency for Pakistani citizens with complete transparency, built to put scam agents out of business. It does not stop at giving information. It runs the whole agency workflow end to end:

- Honest consultation and eligibility assessment (deep reasoning, never fake promises)
- Visa applications: document collection, AI document review, form preparation, submission (via ops/partner), tracking
- Flight tickets and hotel accommodation booking
- Umrah packages (visa + flights + Makkah/Madinah hotels + transport)
- Tour plans and itineraries
- Free Scam Checker (verify what another agent told you)

Read these before writing code. They are the source of truth:

| Doc | What it covers |
|---|---|
| `docs/PRD.md` | Product, users, services, journeys, transparency rules, MVP scope |
| `docs/ARCHITECTURE.md` | System components, services, deployment |
| `docs/DATA_MODEL.md` | Supabase schema, RLS, enums |
| `docs/AGENT.md` | LangGraph agent design, tools, model routing, prompts |
| `docs/CRAWLING.md` | Official-source crawling with Firecrawl/Apify (MVP knowledge layer) |
| `docs/FULFILMENT.md` | How visas, flights, hotels and Umrah actually get booked and submitted |
| `docs/UI_I18N.md` | Screens, English/Urdu, RTL, streaming UX |
| `docs/SECURITY.md` | Document security, PII, audit, compliance guardrails |
| `docs/BUILD_PLAN.md` | Phased milestones and acceptance criteria — **build in this order** |

## Stack

- **Frontend:** Next.js (App Router, TypeScript), Tailwind, shadcn/ui, next-intl for i18n
- **Backend API + agent:** FastAPI (Python 3.12), LangGraph, Anthropic SDK
- **DB / auth / storage:** Supabase (Postgres, Auth, Storage, RLS, Realtime)
- **Background jobs:** a Postgres-backed queue (pg-boss style via `jobs` table) or Celery + Redis. Start with the `jobs` table + a worker process.
- **Crawling:** Firecrawl (primary), Apify actors (JS-heavy or blocked pages)
- **Flights/hotels:** provider adapters (see `docs/FULFILMENT.md`). Start with a sandbox provider.
- **Payments:** Pakistani gateway adapter (Safepay / PayFast / JazzCash / Easypaisa — verify which one we get a merchant account with). Start with manual bank-transfer + receipt upload.
- **Hosting:** Vercel (Next.js), Railway (FastAPI API + worker). In Railway always deploy to the `hamzaabidchaudhary1's Projects` workspace.

## Non-negotiable product rules (enforce in code AND prompts)

1. **No guarantees.** Nothing in the UI, emails, or agent output may promise a visa approval. Add a lint/test that scans agent output templates for "guarantee", "100%", "confirm visa" etc.
2. **Every factual claim about a policy, fee or requirement cites an official source + "last verified" timestamp.** If the agent has no fresh source, it says so and triggers a live fetch, it does not guess.
3. **Itemised pricing.** Every quote is a list of line items: government fee, VFS/TLS fee, flight, hotel, transport, insurance, *our service fee*. Never a single lump sum.
4. **Honest odds.** The eligibility assessment must state weaknesses plainly, even if it loses the sale.
5. **No hidden actions.** Every submission, booking, or payment requires explicit user confirmation in the UI, and every action is logged in `case_events` visible to the user.
6. **Real reference numbers.** When something is submitted/booked, the user sees the actual portal/PNR/booking reference.
7. **Humans approve irreversible steps** in the MVP (visa submission, ticket issuance, payments out). The agent prepares; ops approves.

## Coding conventions

- TypeScript strict; Python with type hints + pydantic v2 models.
- All user-facing strings go through i18n (`en`, `ur`). No hard-coded English in components.
- All money stored as integer minor units + currency code (`PKR`, `USD`, `SAR`, `EUR`, `GBP`, `AED`).
- All timestamps `timestamptz` in UTC; display in `Asia/Karachi`.
- Every external provider behind an adapter interface so we can swap it (`FlightProvider`, `HotelProvider`, `PaymentProvider`, `CrawlProvider`).
- Secrets only via env vars. Never log documents, passport numbers or CNICs.
- Write tests for: pricing math, policy freshness logic, agent guardrails, RLS policies.

## Repo layout (target)

```
/apps/web            Next.js frontend (customer app + ops console under /ops)
/services/api        FastAPI: REST + SSE streaming, auth via Supabase JWT
/services/agent      LangGraph graph, tools, prompts
/services/worker     job runner: crawls, doc review, provider polling
/packages/shared     shared types / JSON schemas
/supabase            migrations, seed, RLS policies
/docs                specs (this folder)
```
