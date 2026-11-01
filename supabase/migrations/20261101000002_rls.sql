-- Row-level security. docs/DATA_MODEL.md "RLS rules" + docs/SECURITY.md "Access control".
-- Principle: customers read their own rows; anything that changes a case (status, quotes,
-- payments, bookings, events) is written by the API with the service role, so every change
-- is validated and logged. Direct client writes are limited to their own travellers/profile.

-- role helpers (security definer so policies don't recurse into profiles RLS)
create or replace function public.app_role() returns text
language sql stable security definer set search_path = public as $$
  select coalesce((select role from public.profiles where id = auth.uid()), 'anon')
$$;

create or replace function public.is_staff() returns boolean
language sql stable security definer set search_path = public as $$
  select public.app_role() in ('ops','admin')
$$;

create or replace function public.my_partner_id() returns uuid
language sql stable security definer set search_path = public as $$
  select partner_id from public.profiles where id = auth.uid() and role = 'partner'
$$;

create or replace function public.owns_case(p_case uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.cases where id = p_case and owner_id = auth.uid())
$$;

create or replace function public.partner_case(p_case uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.cases
    where id = p_case and partner_id is not null and partner_id = public.my_partner_id()
  )
$$;

create or replace function public.can_read_case(p_case uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.owns_case(p_case) or public.is_staff() or public.partner_case(p_case)
$$;

-- enable RLS everywhere
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke insert, update, delete, truncate on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to anon, authenticated', t);
  end loop;
end $$;

-- ---------------------------------------------------------------- profiles
create policy profiles_self_read on public.profiles for select
  using (id = auth.uid() or public.is_staff());
create policy profiles_self_update on public.profiles for update
  using (id = auth.uid()) with check (id = auth.uid());
-- column-level: a user can never change their own role or partner link
grant update (full_name, phone, preferred_locale, keep_documents) on public.profiles to authenticated;

-- ---------------------------------------------------------------- travellers
create policy travellers_owner_all on public.travellers for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy travellers_staff_read on public.travellers for select using (public.is_staff());
create policy travellers_partner_read on public.travellers for select using (
  exists (select 1 from public.case_travellers ct
          where ct.traveller_id = travellers.id and public.partner_case(ct.case_id)));
-- encrypted ID columns are only ever written by the API (it holds the key): column grants
grant insert (owner_id, full_name_as_passport, date_of_birth, gender, nationality, passport_expiry, relationship_to_owner),
      update (full_name_as_passport, date_of_birth, gender, nationality, passport_expiry, relationship_to_owner),
      delete on public.travellers to authenticated;

create policy tprofiles_owner_all on public.traveller_profiles for all
  using (exists (select 1 from public.travellers t where t.id = traveller_id and t.owner_id = auth.uid()))
  with check (exists (select 1 from public.travellers t where t.id = traveller_id and t.owner_id = auth.uid()));
create policy tprofiles_staff_read on public.traveller_profiles for select using (public.is_staff());
grant insert, update, delete on public.traveller_profiles to authenticated;

-- ---------------------------------------------------------------- cases & children
create policy cases_read on public.cases for select using (
  owner_id = auth.uid() or public.is_staff()
  or (partner_id is not null and partner_id = public.my_partner_id()));

create policy case_travellers_read on public.case_travellers for select
  using (public.can_read_case(case_id));

create policy case_events_owner_read on public.case_events for select
  using (visible_to_user and public.owns_case(case_id));
create policy case_events_staff_read on public.case_events for select using (public.is_staff());
create policy case_events_partner_read on public.case_events for select
  using (visible_to_user and public.partner_case(case_id));

create policy documents_read on public.documents for select
  using (deleted_at is null and (public.owns_case(case_id) or public.is_staff()));

create policy quotes_read on public.quotes for select using (public.can_read_case(case_id));
create policy qli_read on public.quote_line_items for select using (
  exists (select 1 from public.quotes q where q.id = quote_id and public.can_read_case(q.case_id)));

create policy bookings_read on public.bookings for select using (public.can_read_case(case_id));
create policy payments_read on public.payments for select
  using (public.owns_case(case_id) or public.is_staff());

-- ---------------------------------------------------------------- public knowledge
create policy sources_public on public.sources for select using (true);
create policy snapshots_public on public.source_snapshots for select using (true);
create policy policy_records_public on public.policy_records for select
  using (status <> 'disputed' or public.is_staff());
create policy allowed_domains_public on public.allowed_domains for select using (true);
create policy service_fees_public on public.service_fees for select using (active or public.is_staff());
create policy refund_policies_public on public.refund_policies for select using (true);

-- ---------------------------------------------------------------- partners
create policy partners_read on public.partners for select
  using (public.is_staff() or id = public.my_partner_id());

-- ---------------------------------------------------------------- staff-only
create policy ops_tasks_staff on public.ops_tasks for select using (public.is_staff());
create policy jobs_staff on public.jobs for select using (public.is_staff());
create policy scheduled_jobs_staff on public.scheduled_jobs for select using (public.is_staff());
create policy audit_staff on public.audit_log for select using (public.app_role() = 'admin');
create policy llm_usage_staff on public.llm_usage for select using (public.is_staff());

-- scam checks: anonymous; read back only through the API (by session id). Staff can read.
create policy scam_checks_staff on public.scam_checks for select using (public.is_staff());

-- ---------------------------------------------------------------- Supabase extras
do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'storage') then
    insert into storage.buckets (id, name, public) values ('documents', 'documents', false)
      on conflict (id) do update set public = false;
    insert into storage.buckets (id, name, public) values ('receipts', 'receipts', false)
      on conflict (id) do update set public = false;
  end if;
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.case_events, public.cases;
  end if;
end $$;
