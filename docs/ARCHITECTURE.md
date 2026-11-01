# Architecture

## Components

```
┌────────────────────────────┐
│ Next.js (Vercel)           │  customer app (en/ur) + /ops console
└─────────────┬──────────────┘
              │ HTTPS + SSE (agent streaming)
┌─────────────▼──────────────┐
│ FastAPI API (Railway)      │  auth (Supabase JWT), cases, quotes, uploads,
│                            │  /chat SSE endpoint → LangGraph agent
└──────┬───────────┬─────────┘
       │           │ enqueue jobs
       │     ┌─────▼──────────────────┐
       │     │ Worker (Railway)       │  crawls, doc review, provider polling,
       │     │                        │  notifications, scheduled jobs
       │     └─────┬──────────────────┘
       │           │
┌──────▼───────────▼─────────┐     ┌──────────────────────────────┐
│ Supabase                   │     │ External providers (adapters) │
│ Postgres + RLS             │     │ Anthropic (LLM)               │
│ Auth                       │     │ Firecrawl / Apify (crawling)  │
│ Storage (private buckets)  │     │ Flight provider               │
│ Realtime (case updates)    │     │ Hotel provider                │
└────────────────────────────┘     │ Payment gateway (PK)          │
                                   │ Email (Resend) / SMS          │
                                   └──────────────────────────────┘
```

## Services

### apps/web (Next.js)
- Customer routes: `/[locale]/` landing, `/chat`, `/scam-check`, `/visa/[country]`, `/umrah`, `/flights`, `/hotels`, `/cases`, `/cases/[id]`, `/account`.
- Ops routes: `/ops/cases`, `/ops/cases/[id]`, `/ops/sources` (crawl review), `/ops/partners`. Role-gated (`ops`, `admin`).
- Subscribes to Supabase Realtime on `case_events` for live case timelines.

### services/api (FastAPI)
- `POST /chat` → SSE stream of agent events (`progress`, `token`, `tool_call`, `card`, `done`). See `docs/AGENT.md`.
- `POST /scam-check` (no auth, rate-limited).
- CRUD: cases, travellers, documents (signed upload URLs), quotes, bookings, payments.
- Webhooks: payment gateway, flight/hotel provider.
- Verifies Supabase JWT; uses service-role key only server-side.

### services/agent (LangGraph)
- Graph defined in `docs/AGENT.md`. Checkpointer: Postgres (LangGraph Postgres saver) so conversations and long-running reasoning survive restarts.

### services/worker
- Polls `jobs` table (`SELECT … FOR UPDATE SKIP LOCKED`).
- Job types: `crawl_source`, `extract_policy`, `review_documents`, `poll_booking_status`, `send_notification`, `expire_quote`, `deep_assessment`.
- Scheduler: cron-like rows in `scheduled_jobs` (daily crawls, quote expiry).

## Latency strategy (no voice; deep reasoning is fine)

- Fast path: simple factual questions → `claude-haiku-5-5`/`claude-sonnet-5-5` over cached source snapshots, < 5s.
- Deep path: eligibility assessment, document review, package planning → `claude-opus-5-5` (configurable) with extended thinking. Run as a job when > ~20s; stream progress steps to the UI; notify on completion.
- Always stream human-readable progress ("Checking Schengen proof-of-funds rules…") so latency reads as thoroughness.

## Environments & deploy

- `dev`, `staging`, `prod` Supabase projects.
- Railway: two services (`api`, `worker`) in workspace **hamzaabidchaudhary1's Projects**.
- Vercel for web. Env vars documented in `.env.example` per app.

## Key env vars

```
ANTHROPIC_API_KEY
MODEL_FAST=claude-haiku-5-5
MODEL_STANDARD=claude-sonnet-5-5
MODEL_DEEP=claude-opus-5-5
SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY
FIRECRAWL_API_KEY
APIFY_TOKEN
FLIGHT_PROVIDER=sandbox|duffel|partner
HOTEL_PROVIDER=sandbox|...
PAYMENT_PROVIDER=manual|safepay|payfast|...
RESEND_API_KEY
DOCS_ENCRYPTION_KEY
```
