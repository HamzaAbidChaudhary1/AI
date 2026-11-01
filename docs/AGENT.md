# Agent Design (LangGraph)

## Goals
A deep-reasoning travel agent that consults honestly, assesses eligibility, plans trips, prepares applications and drives bookings, but never fakes certainty and never takes irreversible actions without explicit user confirmation (and ops approval in MVP).

## Model routing

| Task | Model (env) | Notes |
|---|---|---|
| Intent routing, small talk, quick facts | `MODEL_FAST` | low latency |
| Quotes, itinerary drafts, scam check | `MODEL_STANDARD` | |
| Eligibility assessment, document review, Umrah package planning, refusal analysis | `MODEL_DEEP` | extended thinking on; may run as background job |

## Graph

```
            ┌──────────┐
 user msg → │  router  │──► quick_answer ─────────────┐
            └────┬─────┘                              │
                 ├──► consult (gather profile/trip)   │
                 ├──► assess_eligibility (deep)       │
                 ├──► plan_trip / plan_umrah (deep)   │
                 ├──► build_quote                     ├──► respond (stream, cite, en/ur)
                 ├──► document_review (deep, job)     │
                 ├──► prepare_application_pack        │
                 ├──► booking_flow (search→hold→confirm)
                 └──► scam_check                      │
                                                      ┘
 Any node needing a fact → `ensure_fresh_sources` subgraph (see CRAWLING.md)
 Any irreversible action → `request_user_confirmation` interrupt → `ops_approval` interrupt (MVP)
```

Use LangGraph `interrupt()` for confirmations and ops approvals. State persisted with the Postgres checkpointer keyed by `case_id` (or `session_id` pre-case).

## State (pydantic)

```python
class AgentState(BaseModel):
    locale: Literal["en","ur"]
    user_id: str | None
    case_id: str | None
    service_type: str | None
    destination: str | None
    trip: dict | None              # dates, travellers, budget, preferences
    traveller_profiles: list[dict]
    citations: list[Citation]       # every fact used this turn
    pending_action: dict | None     # what awaits confirmation
    messages: list[AnyMessage]
```

## Tools

Knowledge
- `get_policy(country, visa_type, fields[])` → policy_records + citations; flags stale
- `search_snapshots(query, country?, topic?)` → keyword/full-text search over `source_snapshots` (Postgres FTS; no vectors in MVP)
- `live_fetch(url)` → Firecrawl scrape of an **allow-listed official domain** only; stores a snapshot
- `verify_agent_licence(name_or_number)` → checks crawled BEOE OEP list / FIA notices

Case & documents
- `create_case`, `update_case_status`, `add_case_event`
- `request_documents(case_id, checklist[])`
- `review_documents(case_id)` → enqueues deep job; returns job id
- `generate_application_pack(case_id)` → form field JSON, cover letter, itinerary PDF, document index

Commerce
- `build_quote(case_id, items[])` → itemised quote; service fee from config table, never invented
- `search_flights(origin, dest, dates, pax, cabin)` / `hold_flight` / `issue_ticket*`
- `search_hotels(city, dates, guests, filters)` / `book_hotel*`
- `get_umrah_partner_inventory(dates, pax)` → partner packages/hotels
- `create_payment_request(quote_id)`

`*` = irreversible → requires confirmation interrupt + ops approval.

## System prompt (core, abbreviated — keep full version in `services/agent/prompts/system.md`)

```
You are Rahbar, an honest travel and visa agent for Pakistani citizens.

Rules you never break:
- You never promise or imply a guaranteed visa. Embassies decide. Say so when relevant.
- Every policy, fee, requirement or timeline you state must come from a tool result
  with a source URL. Cite it with its last-verified date. If you have no fresh source,
  say you are checking, call live_fetch, or say you could not verify it.
- Give honest odds. If the profile is weak, say why and what would strengthen it,
  even if the user may not proceed.
- Show prices only as itemised lines from build_quote. Never invent a fee.
- Never submit, book, issue or charge without an explicit user confirmation step.
- Never advise on falsifying documents, fake bank balances, fake employment letters,
  "dummy" sponsorships or any deception. Explain the risk (refusal, ban) instead.
- Work visas and job offers: we do not provide them yet. Explain that legal overseas
  employment from Pakistan goes through BEOE-licensed promoters and how to verify one.
- Reply in the user's selected language ({locale}). In Urdu keep official terms
  (e.g. "proof of funds", "VFS", "NOC", "Schengen") in English in brackets.
- Be warm and plain-spoken; many users are first-time travellers or elderly.
```

## Streaming protocol (SSE from /chat)

```
event: progress   data: {"step":"Checking UK visitor visa fees","step_ur":"..."}
event: token      data: {"text":"..."}
event: citation   data: {"url":"...","title":"...","verified_at":"..."}
event: card       data: {"type":"quote|assessment|checklist|flight_options|hotel_options|confirm_action", ...}
event: job        data: {"job_id":"...","eta_seconds":60}
event: done       data: {}
```

## Guardrail tests (must exist)
- Output never contains guarantee language (en + ur phrases list).
- Quote cards only contain amounts from `build_quote` results.
- Irreversible tools cannot execute without a confirmation record in state.
- Facts without citations are rejected by a post-processing validator → agent retries.
