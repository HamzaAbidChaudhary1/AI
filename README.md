# Rahbar — the honest travel agency

AI-run travel & visa agency for Pakistani citizens: honest consultation, cited requirements and fees,
itemised quotes, document review, application packs, Umrah packages, flights & hotels, and a free Scam
Checker. Specs live in [`CLAUDE.md`](CLAUDE.md) and [`docs/`](docs/) and are the source of truth.

```
apps/web            Next.js 16 (App Router, TS, Tailwind 4, next-intl en/ur + RTL) — customer app + /ops console
services/agent      LangGraph agent, guardrails, crawling, pricing, cases, documents, packs, providers
services/api        FastAPI: REST + SSE /chat, Supabase JWT auth, ops API
services/worker     jobs-table worker: crawls, extraction, document review, quote expiry, retention
supabase            migrations (schema + RLS), seed, local test shim
scripts             local DB reset, crawl-all
```

## Run it locally

Needs Postgres 16, [uv](https://docs.astral.sh/uv/), Node 22 and pnpm. No API keys are required. Without
them the agent runs in **offline mode**: facts come from tools, replies come from bilingual templates, and
crawling uses clearly-labelled **test fixtures** (shown as "TEST DATA" everywhere, never usable in a binding quote).

```bash
uv sync --all-packages && pnpm install
```

```bash
DATABASE_URL=postgresql://postgres@localhost:54322/rahbar scripts/db_reset_local.sh
```

```bash
cat > .env.dev.local.sh <<'EOF'
export DATABASE_URL=postgresql://postgres@localhost:54322/rahbar
export LLM_MODE=offline CRAWL_PROVIDER=fixture DEV_AUTH=true ALLOW_TEST_DATA=true
export SUPABASE_JWT_SECRET=local-dev-jwt-secret-at-least-32-characters-long
export DOCS_ENCRYPTION_KEY=k1:$(python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
export LOCAL_STORAGE_DIR=/tmp/rahbar-dev-storage CORS_ORIGINS=http://localhost:3000
EOF
```

```bash
source .env.dev.local.sh && uv run python scripts/crawl_all.py
```

```bash
source .env.dev.local.sh && uv run uvicorn rahbar_api.app:app --port 8000
```

```bash
source .env.dev.local.sh && uv run rahbar-worker
```

```bash
cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_DEV_AUTH=true pnpm dev
```

Open http://localhost:3000. With `DEV_AUTH=true` (and no `SUPABASE_URL`) the sign-in page lets you log in as a
customer, ops or admin user. The API refuses to mount that route when Supabase is configured.

Set `ANTHROPIC_API_KEY` to have Claude phrase replies (every reply is still validated before it streams), and
`FIRECRAWL_API_KEY` / `APIFY_TOKEN` to crawl the real official pages.

## Tests

```bash
uv run pytest -q          # 86 tests: RLS, guardrails, pricing, freshness, crawl, agent, flows, HTTP API, worker
```

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

Python tests need a local Postgres on port 54322 (`DATABASE_URL` defaults to `.../rahbar_test`, recreated per run).

## How the non-negotiable rules are enforced

| Rule | Where |
|---|---|
| 1. No guarantees | `guardrails.check_no_guarantees` runs on every reply before streaming (negations and quoted scam text allowed); `test_template_lint.py` scans both message catalogues, event strings, declarations and the system prompt |
| 2. Cited facts + last verified | facts only from `policy_records` → snapshot → source; `check_citations`; freshness ≤7d fees/requirements, ≤30d general; stale → `live_fetch`; unverifiable → marked "may be out of date" |
| 3. Itemised pricing | `pricing.build_quote`: third-party lines + our fee from `service_fees` only (cannot be injected); `check_amounts` rejects any amount not from a tool |
| 4. Honest odds | `assessment.assess`: explainable factors, blockers stated plainly; the LLM cannot change the rating |
| 5. No hidden actions | `pending_actions` gate + LangGraph `interrupt()` for confirmation; every step in `case_events` |
| 6. Real references | submission/ticket/partner executors require the provider/portal reference; shown in timeline and Bookings |
| 7. Humans approve irreversible steps | `actions.require_approved` (user confirmation + ops approval; four-eyes for ops-initiated refunds) |

## Build plan status

| Phase | Status |
|---|---|
| 0 Foundations | ✅ schema, RLS + tests, seed, FastAPI + JWT, worker, Next.js en/ur RTL, auth (Supabase email + phone OTP; dev login locally), CI workflow. **Not done:** Supabase projects and Railway/Vercel deploys need your accounts/keys. |
| 1 Crawling | ✅ Firecrawl/Apify/fixture adapters, change detection → new snapshot → policy record → ops review task, FTS, `/ops/sources` diff + verify/dispute. **Source URLs in `supabase/seed/sources.csv` must be verified by a person against the live sites.** |
| 2 Agent + chat | ✅ LangGraph graph, Postgres checkpointer, SSE progress/citations/cards, guardrail validators, model routing via env. |
| 3 Scam Checker | ✅ public `/scam-check`, rate-limited, file upload (images/PDF read by Claude when a key is set), BEOE licence lookup. |
| 4 Cases/quotes/docs | ✅ lifecycle + live timeline, quote builder, upload with signed URLs, encrypted IDs, review job, packs for UK + Türkiye. |
| 5 Ops & fulfilment | ✅ ops queue/case/copy-field pack, approvals, references, refunds, ManualPartnerAdapter + Umrah builder, manual bank transfer. |
| 6 Real providers | ⏳ adapter interfaces + sandbox only. Needs a flight provider/consolidator, a hotel bedbank and a PK payment-gateway merchant account. |
| 7 Hardening | 🟡 Sentry PII redaction, audit log, export/delete, retention job, ToS/Privacy/refund/"how we're different" pages done. Load test, real email/SMS notifications, lawyer review of legal texts still to do. |

Placeholders to replace before any real customer: service fees (`seed.sql`), FX rates (admin API `POST /ops/fx`), bank
account details (`providers/payments.py`), demo Umrah partner and inventory, and the brand name.
