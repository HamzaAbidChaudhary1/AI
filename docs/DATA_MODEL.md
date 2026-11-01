# Data Model (Supabase / Postgres)

All tables have `id uuid pk default gen_random_uuid()`, `created_at timestamptz default now()`, `updated_at timestamptz`. Money = `amount_minor bigint` + `currency char(3)`.

## Users & people

```sql
profiles (
  id uuid pk references auth.users,
  full_name text, phone text, preferred_locale text check (preferred_locale in ('en','ur')) default 'en',
  role text check (role in ('customer','ops','admin','partner')) default 'customer'
)

travellers (            -- a profile can manage several travellers (e.g. parents for Umrah)
  owner_id uuid references profiles,
  full_name_as_passport text, date_of_birth date, gender text,
  nationality text default 'PK',
  passport_number_enc bytea,      -- encrypted, see SECURITY.md
  passport_expiry date,
  cnic_enc bytea,
  relationship_to_owner text
)

traveller_profiles (    -- inputs for eligibility assessment
  traveller_id uuid references travellers,
  employment_status text, employer text, monthly_income_minor bigint, income_currency char(3),
  travel_history jsonb,           -- [{country, year, visa_type}]
  prior_refusals jsonb,           -- [{country, year, reason}]
  sponsor jsonb, ties_to_pakistan jsonb
)
```

## Knowledge layer (crawling MVP — see CRAWLING.md)

```sql
sources (
  url text unique, authority text,   -- 'gov.uk', 'vfsglobal', 'beoe.gov.pk', 'nusuk' ...
  country text, topic text,          -- 'visit_visa','umrah','fees','biometrics','scam_warning'
  crawl_method text check (crawl_method in ('firecrawl','apify')),
  apify_actor text, crawl_frequency interval default '1 day',
  is_official boolean default true, active boolean default true
)

source_snapshots (
  source_id uuid references sources,
  fetched_at timestamptz, content_markdown text, content_hash text,
  http_status int, changed_from_previous boolean
)

policy_records (       -- structured extraction from snapshots
  country text, visa_type text, field text,   -- e.g. 'proof_of_funds', 'gov_fee', 'processing_time'
  value jsonb, source_snapshot_id uuid references source_snapshots,
  status text check (status in ('auto','verified','stale','disputed')) default 'auto',
  verified_by uuid references profiles, verified_at timestamptz
)
```

## Commerce & cases

```sql
service_type enum: 'visit_visa','umrah_package','flight','hotel','tour','scam_check'

cases (
  owner_id uuid references profiles,
  service_type service_type, destination_country text, purpose text,
  status case_status,     -- see below
  strength_rating text check (strength_rating in ('strong','fair','weak')),
  assessment jsonb,       -- full reasoning output incl. citations
  assigned_ops_id uuid references profiles,
  partner_id uuid references partners
)

case_status enum:
 'consulting','assessed','quoted','accepted','collecting_documents','documents_review',
 'pack_ready','awaiting_user_confirmation','submitted','biometrics_scheduled',
 'in_process','decision_approved','decision_refused','booked','completed','cancelled','refunded'

case_travellers (case_id, traveller_id)

case_events (           -- user-visible audit timeline
  case_id uuid, actor_type text check (actor_type in ('ai','ops','partner','user','system')),
  actor_id uuid, event_type text, message_en text, message_ur text,
  data jsonb, visible_to_user boolean default true
)

documents (
  case_id uuid, traveller_id uuid, doc_type text,   -- passport, cnic, bank_statement, photo, noc, ...
  storage_path text, mime text, sha256 text,
  review_status text check (review_status in ('pending','ok','issues','rejected')),
  review_findings jsonb, uploaded_by uuid
)

quotes (
  case_id uuid, version int, valid_until timestamptz, status text, -- draft/sent/accepted/expired
  total_minor bigint, currency char(3), fx_rates jsonb
)

quote_line_items (
  quote_id uuid, kind text,      -- gov_fee, vfs_fee, flight, hotel, transport, insurance, ziyarat, service_fee
  description_en text, description_ur text,
  amount_minor bigint, currency char(3),
  source_url text, source_verified_at timestamptz,
  payee text                     -- 'government', 'vfs', 'airline', 'hotel', 'partner', 'rahbar'
)

bookings (
  case_id uuid, kind text check (kind in ('flight','hotel','visa_application','transport','insurance')),
  provider text, provider_ref text, status text, details jsonb, documents jsonb  -- e-ticket, voucher
)

payments (
  case_id uuid, quote_id uuid, provider text, provider_ref text,
  amount_minor bigint, currency char(3),
  status text check (status in ('pending','received','verified','refunded','failed')),
  receipt_path text
)

partners (
  name text, kind text,   -- 'umrah_operator','travel_agency','consolidator'
  licence_number text, licence_authority text, licence_expiry date,
  contract_terms jsonb, active boolean
)

scam_checks (           -- anonymous allowed
  session_id text, input_text text, input_files jsonb, result jsonb, converted_user_id uuid
)

jobs (type text, payload jsonb, status text, run_at timestamptz, attempts int, last_error text)
```

## RLS rules

- Customers: read/write only rows where `owner_id = auth.uid()` (and joined children). `case_events` readable only when `visible_to_user`.
- Ops/admin: full read on cases; write via API only.
- Partners: read cases where `partner_id` matches their partner org; no access to other cases.
- `sources`, `policy_records` (status ≠ 'disputed'): public read.
- Storage bucket `documents`: private; access via short-lived signed URLs issued by API after ownership check.
