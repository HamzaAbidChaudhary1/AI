-- Snapshot provenance + freshness.
-- provider: which adapter fetched it ('firecrawl' | 'apify' | 'fixture'). Fixture content is test
--   data and is labelled as such everywhere; it can never be used in a binding quote.
-- last_seen_at: when the page was last fetched with identical content. Unchanged pages do not
--   create new snapshot rows, but they do count as re-verified for freshness rules.
alter table public.source_snapshots
  add column provider text not null default 'firecrawl',
  add column last_seen_at timestamptz not null default now();
update public.source_snapshots set last_seen_at = fetched_at;
