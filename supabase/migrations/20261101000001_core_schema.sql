-- Rahbar core schema. Source of truth: docs/DATA_MODEL.md
-- Money: amount_minor bigint + currency char(3). Timestamps: timestamptz (UTC).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create domain public.currency_code as char(3)
  check (value in ('PKR','USD','SAR','EUR','GBP','AED','TRY','MYR'));

-- ---------------------------------------------------------------------------
-- enums
-- ---------------------------------------------------------------------------
create type public.service_type as enum
  ('visit_visa','umrah_package','flight','hotel','tour','scam_check');

create type public.case_status as enum (
  'consulting','assessed','quoted','accepted','collecting_documents','documents_review',
  'pack_ready','awaiting_user_confirmation','submitted','biometrics_scheduled',
  'in_process','decision_approved','decision_refused','booked','completed','cancelled','refunded'
);

-- ---------------------------------------------------------------------------
-- partners (declared first: profiles.partner_id references it)
-- ---------------------------------------------------------------------------
create table public.partners (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  name text not null,
  kind text not null check (kind in ('umrah_operator','travel_agency','consolidator')),
  licence_number text,
  licence_authority text,
  licence_expiry date,
  contract_terms jsonb not null default '{}'::jsonb,
  active boolean not null default true
);

-- ---------------------------------------------------------------------------
-- users & people
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  full_name text,
  phone text,
  preferred_locale text not null default 'en' check (preferred_locale in ('en','ur')),
  role text not null default 'customer' check (role in ('customer','ops','admin','partner')),
  partner_id uuid references public.partners (id), -- set for role = 'partner'
  keep_documents boolean not null default false     -- opt-out of retention deletion
);

create table public.travellers (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  owner_id uuid not null references public.profiles (id) on delete cascade,
  full_name_as_passport text not null,
  date_of_birth date,
  gender text,
  nationality text not null default 'PK',
  passport_number_enc bytea,   -- AES-GCM, app-level (docs/SECURITY.md)
  passport_expiry date,
  cnic_enc bytea,
  relationship_to_owner text
);
create index on public.travellers (owner_id);

create table public.traveller_profiles (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  traveller_id uuid not null unique references public.travellers (id) on delete cascade,
  employment_status text,
  employer text,
  monthly_income_minor bigint check (monthly_income_minor is null or monthly_income_minor >= 0),
  income_currency public.currency_code,
  travel_history jsonb not null default '[]'::jsonb,
  prior_refusals jsonb not null default '[]'::jsonb,
  sponsor jsonb,
  ties_to_pakistan jsonb
);

-- ---------------------------------------------------------------------------
-- knowledge layer (docs/CRAWLING.md)
-- ---------------------------------------------------------------------------
create table public.allowed_domains (
  domain text primary key,          -- e.g. 'gov.uk'; subdomains allowed
  authority text not null,
  created_at timestamptz not null default now()
);

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  url text not null unique,
  title text,
  authority text not null,
  country text,
  topic text not null,
  visa_type text,
  crawl_method text not null default 'firecrawl' check (crawl_method in ('firecrawl','apify')),
  apify_actor text,
  crawl_frequency interval not null default '1 day',
  is_official boolean not null default true,
  active boolean not null default true,
  last_crawled_at timestamptz,
  last_crawl_status text
);

create table public.source_snapshots (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  source_id uuid not null references public.sources (id) on delete cascade,
  fetched_at timestamptz not null default now(),
  content_markdown text not null,
  content_hash text not null,
  http_status int,
  changed_from_previous boolean not null default false,
  fts tsvector generated always as (to_tsvector('english', coalesce(content_markdown, ''))) stored
);
create index on public.source_snapshots (source_id, fetched_at desc);
create index source_snapshots_fts_idx on public.source_snapshots using gin (fts);

create table public.policy_records (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  country text not null,
  visa_type text not null,
  field text not null,
  value jsonb,
  source_snapshot_id uuid references public.source_snapshots (id) on delete set null,
  status text not null default 'auto' check (status in ('auto','verified','stale','disputed')),
  verified_by uuid references public.profiles (id),
  verified_at timestamptz
);
create index on public.policy_records (country, visa_type, field, status);

-- ---------------------------------------------------------------------------
-- commerce config
-- ---------------------------------------------------------------------------
create table public.service_fees (          -- our fee: fixed per service, never invented
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  service_type public.service_type not null,
  destination_country text,                 -- null = applies to all
  amount_minor bigint not null check (amount_minor >= 0),
  currency public.currency_code not null default 'PKR',
  per text not null default 'traveller' check (per in ('traveller','case','booking')),
  description_en text not null,
  description_ur text not null,
  active boolean not null default true,
  unique (service_type, destination_country)
);

create table public.refund_policies (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  service_type public.service_type not null unique,
  rules jsonb not null,                      -- [{before_status, refund_percent_service_fee}]
  text_en text not null,
  text_ur text not null
);

-- ---------------------------------------------------------------------------
-- cases
-- ---------------------------------------------------------------------------
create table public.cases (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  owner_id uuid not null references public.profiles (id) on delete cascade,
  service_type public.service_type not null,
  destination_country text,
  purpose text,
  trip jsonb not null default '{}'::jsonb,
  status public.case_status not null default 'consulting',
  strength_rating text check (strength_rating in ('strong','fair','weak')),
  assessment jsonb,
  assigned_ops_id uuid references public.profiles (id),
  partner_id uuid references public.partners (id),
  completed_at timestamptz
);
create index on public.cases (owner_id);
create index on public.cases (status);

create table public.case_travellers (
  case_id uuid not null references public.cases (id) on delete cascade,
  traveller_id uuid not null references public.travellers (id) on delete cascade,
  primary key (case_id, traveller_id)
);

create table public.case_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  actor_type text not null check (actor_type in ('ai','ops','partner','user','system')),
  actor_id uuid,
  event_type text not null,
  message_en text not null,
  message_ur text not null,
  data jsonb not null default '{}'::jsonb,
  visible_to_user boolean not null default true
);
create index on public.case_events (case_id, created_at);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  traveller_id uuid references public.travellers (id) on delete set null,
  doc_type text not null,
  storage_path text not null,
  mime text,
  sha256 text,
  extracted jsonb,                     -- structured fields read from the document (no raw IDs)
  review_status text not null default 'pending'
    check (review_status in ('pending','ok','issues','rejected')),
  review_findings jsonb not null default '[]'::jsonb,
  uploaded_by uuid references public.profiles (id),
  deleted_at timestamptz
);
create index on public.documents (case_id);

create table public.quotes (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  version int not null default 1,
  valid_until timestamptz not null,
  status text not null default 'draft' check (status in ('draft','sent','accepted','expired','superseded')),
  total_minor bigint not null,
  currency public.currency_code not null default 'PKR',
  fx_rates jsonb not null default '{}'::jsonb,
  accepted_at timestamptz,
  unique (case_id, version)
);

create table public.quote_line_items (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  quote_id uuid not null references public.quotes (id) on delete cascade,
  position int not null default 0,
  kind text not null check (kind in
    ('gov_fee','vfs_fee','flight','hotel','transport','insurance','ziyarat','service_fee','visa_fee','other')),
  description_en text not null,
  description_ur text not null,
  amount_minor bigint not null check (amount_minor >= 0),
  currency public.currency_code not null,
  amount_quote_currency_minor bigint not null,  -- converted with quotes.fx_rates
  source_url text,
  source_verified_at timestamptz,
  payee text not null check (payee in ('government','vfs','tls','airline','hotel','partner','insurer','transport','rahbar')),
  paid_directly_by_user boolean not null default false
);

create table public.bookings (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  kind text not null check (kind in ('flight','hotel','visa_application','transport','insurance','umrah_package')),
  provider text not null,
  provider_ref text,
  status text not null default 'pending',
  details jsonb not null default '{}'::jsonb,
  documents jsonb not null default '[]'::jsonb,
  idempotency_key text unique
);

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  quote_id uuid references public.quotes (id),
  provider text not null,
  provider_ref text,
  amount_minor bigint not null check (amount_minor >= 0),
  currency public.currency_code not null,
  status text not null default 'pending' check (status in ('pending','received','verified','refunded','failed')),
  receipt_path text,
  direction text not null default 'in' check (direction in ('in','refund')),
  reason text,
  idempotency_key text unique
);

create table public.scam_checks (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  session_id text not null,
  input_text text,
  input_files jsonb not null default '[]'::jsonb,
  result jsonb,
  converted_user_id uuid references public.profiles (id)
);
create index on public.scam_checks (session_id, created_at);

-- ---------------------------------------------------------------------------
-- ops, jobs, audit
-- ---------------------------------------------------------------------------
create table public.ops_tasks (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  kind text not null,              -- policy_change_review, submit_visa, verify_payment, issue_ticket, partner_booking, refund
  case_id uuid references public.cases (id) on delete cascade,
  policy_record_id uuid references public.policy_records (id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'open' check (status in ('open','done','rejected')),
  resolved_by uuid references public.profiles (id),
  resolved_at timestamptz,
  due_at timestamptz
);
create index on public.ops_tasks (status, kind);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued' check (status in ('queued','running','done','failed')),
  run_at timestamptz not null default now(),
  attempts int not null default 0,
  max_attempts int not null default 3,
  last_error text,
  result jsonb,
  locked_at timestamptz
);
create index jobs_ready_idx on public.jobs (run_at) where status = 'queued';

create table public.scheduled_jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  name text not null unique,
  type text not null,
  payload jsonb not null default '{}'::jsonb,
  every interval not null,
  next_run_at timestamptz not null default now(),
  active boolean not null default true
);

create table public.audit_log (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  actor_id uuid,
  actor_role text,
  action text not null,
  entity text not null,
  entity_id uuid,
  data jsonb not null default '{}'::jsonb
);

create table public.llm_usage (     -- cost dashboard per case
  id bigserial primary key,
  created_at timestamptz not null default now(),
  case_id uuid references public.cases (id) on delete set null,
  session_id text,
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  node text
);

-- updated_at triggers on every table that has the column
do $$
declare t text;
begin
  for t in
    select c.table_name from information_schema.columns c
    where c.table_schema = 'public' and c.column_name = 'updated_at'
  loop
    execute format(
      'create trigger set_updated_at before update on public.%I for each row execute function public.set_updated_at()', t);
  end loop;
end $$;

-- new auth user -> profile row
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, full_name, phone, preferred_locale)
  values (
    new.id,
    new.raw_user_meta_data ->> 'full_name',
    new.phone,
    coalesce(nullif(new.raw_user_meta_data ->> 'preferred_locale', ''), 'en')
  )
  on conflict (id) do nothing;
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
