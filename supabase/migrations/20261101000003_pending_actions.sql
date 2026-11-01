-- Irreversible actions (visa submission, ticket issue, hotel booking, payments out, refunds)
-- go through a two-step gate: explicit user confirmation, then ops approval (MVP).
-- Executors refuse to run without an 'approved' row here. docs/AGENT.md, CLAUDE.md rules 5 & 7.
create table public.pending_actions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  case_id uuid not null references public.cases (id) on delete cascade,
  kind text not null check (kind in
    ('submit_visa','issue_ticket','book_hotel','book_umrah','pay_out','refund','accept_quote')),
  summary_en text not null,
  summary_ur text not null,
  payload jsonb not null default '{}'::jsonb,
  requires_ops boolean not null default true,
  status text not null default 'awaiting_user'
    check (status in ('awaiting_user','awaiting_ops','approved','executed','rejected','cancelled')),
  user_confirmed_by uuid references public.profiles (id),
  user_confirmed_at timestamptz,
  declarations jsonb not null default '[]'::jsonb,   -- per-declaration checkbox log
  ops_approved_by uuid references public.profiles (id),
  ops_approved_at timestamptz,
  executed_at timestamptz,
  result jsonb
);
create index on public.pending_actions (case_id, status);
create trigger set_updated_at before update on public.pending_actions
  for each row execute function public.set_updated_at();

alter table public.pending_actions enable row level security;
alter table public.pending_actions force row level security;
revoke insert, update, delete, truncate on public.pending_actions from anon, authenticated;
grant select on public.pending_actions to authenticated;
create policy pending_actions_read on public.pending_actions for select
  using (public.owns_case(case_id) or public.is_staff());
