#!/usr/bin/env bash
# Recreate the LOCAL dev/test database: Supabase shim + migrations + seed.
# Usage: DATABASE_URL=postgresql://postgres@localhost:54322/rahbar scripts/db_reset_local.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${DATABASE_URL:-postgresql://postgres@localhost:54322/rahbar}"
DB="${URL##*/}"; ADMIN="${URL%/*}/postgres"
psql "$ADMIN" -qc "drop database if exists \"$DB\" with (force)" -c "create database \"$DB\""
psql "$URL" -q -v ON_ERROR_STOP=1 -f "$ROOT/supabase/tests/00_local_supabase_shim.sql"
for f in "$ROOT"/supabase/migrations/*.sql; do psql "$URL" -q -v ON_ERROR_STOP=1 -f "$f"; done
psql "$URL" -q -v ON_ERROR_STOP=1 -f "$ROOT/supabase/seed/seed.sql"
psql "$URL" -q -v ON_ERROR_STOP=1 <<SQL
create temp table s (url text, title text, authority text, country text, topic text, visa_type text, crawl_method text, days int);
\copy s from '$ROOT/supabase/seed/sources.csv' with (format csv, header true)
insert into public.sources (url, title, authority, country, topic, visa_type, crawl_method, crawl_frequency)
select url, title, authority, nullif(country,''), topic, nullif(visa_type,''), crawl_method, make_interval(days => days) from s
on conflict (url) do nothing;
SQL
echo "database $DB ready"
