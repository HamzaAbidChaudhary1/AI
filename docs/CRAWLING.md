# Crawling (MVP knowledge layer)

MVP decision: **no vector RAG.** Knowledge comes from crawling allow-listed official sources with Firecrawl and Apify, storing snapshots, extracting structured policy records, and searching with Postgres full-text search. A curated RAG layer is a future phase (see end).

## Source registry

`sources` table, seeded from `supabase/seed/sources.csv`. Only allow-listed domains may ever be fetched by the agent's `live_fetch`.

Seed categories (fill URLs during build; verify each is the official page):
- **Destination governments:** UK (gov.uk visit visa, fees), Schengen country embassies in Pakistan, UAE ICP/GDRFA, Türkiye e-visa, Malaysia, Saudi (visit/Umrah, Nusuk).
- **Application centres:** VFS Global / TLScontact Pakistan pages per country (fees, document checklists, appointment info).
- **Pakistan:** BEOE (licensed OEP lists, warnings, notices), FIA (notices, complaint channels), Ministry of Religious Affairs (Umrah operator rules), passport office.
- **Scam intelligence:** BEOE/FIA public warnings, official embassy fraud-warning pages.

## Pipeline

```
scheduler ─► crawl_source job ─► Firecrawl scrape (markdown)
                               └► fallback: Apify actor (JS-heavy / blocked)
           ─► hash content ─► if changed: new source_snapshot (changed_from_previous=true)
           ─► extract_policy job (MODEL_STANDARD, JSON schema output)
           ─► upsert policy_records (status='auto'), mark old ones 'stale'
           ─► if a field value changed: create ops review task + notify
```

- Default frequency: daily for fees/requirements pages; weekly for general pages.
- Respect robots.txt and rate limits; identify with a proper user agent.
- Store `content_markdown` only (no raw HTML) to keep size small.

## Structured extraction

Per (country, visa_type) extract fields such as:
`gov_fee`, `service_centre_fee`, `processing_time`, `validity`, `max_stay`, `required_documents[]`, `proof_of_funds`, `biometrics_required`, `interview_required`, `photo_specs`, `insurance_required`, `apply_from` (e.g. VFS Islamabad/Lahore/Karachi).

Extraction prompt must return `null` for anything not explicitly stated on the page. Never infer.

## Freshness rules used by the agent

- `policy_record` used in an answer must have a snapshot ≤ 7 days old for fees/requirements, ≤ 30 days for general info.
- If stale → agent calls `live_fetch` on the source, re-extracts, then answers.
- If live fetch fails → agent tells the user it couldn't verify right now, shows last known value with its date clearly marked as possibly outdated, and does not quote it in a binding quote.
- Quotes may only use records with status `verified` (ops-approved) or `auto` + fresh ≤ 7 days.

## Ops console: `/ops/sources`
- List sources, last crawl, status, changes.
- Diff view of changed snapshots.
- Approve / dispute extracted policy records.
- Add new source URL (domain must be on allow-list).

## Future: curated RAG (not MVP)
Move from raw crawl to a curated, versioned knowledge base: human-verified policy documents chunked and embedded (pgvector), with version history and approval workflow. Crawling remains the change-detection layer feeding it.
