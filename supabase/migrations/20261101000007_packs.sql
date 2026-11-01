-- Generated application packs (form data, cover letter, itinerary, document index).
create table public.application_packs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  version int not null default 1,
  content jsonb not null,
  unique (case_id, version)
);
create trigger set_updated_at before update on public.application_packs for each row execute function public.set_updated_at();
alter table public.application_packs enable row level security;
alter table public.application_packs force row level security;
revoke insert, update, delete, truncate on public.application_packs from anon, authenticated;
grant select on public.application_packs to authenticated;
create policy packs_read on public.application_packs for select using (public.owns_case(case_id) or public.is_staff());
