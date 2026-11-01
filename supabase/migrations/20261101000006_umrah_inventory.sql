-- Umrah partner inventory, entered by ops from the licensed partner (ManualPartnerAdapter).
create table public.umrah_inventory (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  partner_id uuid not null references public.partners (id),
  kind text not null check (kind in ('visa','hotel_makkah','hotel_madinah','transport','ziyarat','insurance','flight')),
  name text not null,
  details jsonb not null default '{}'::jsonb,       -- stars, distance_to_haram_m (as provided by partner), room, airline...
  unit_amount_minor bigint not null check (unit_amount_minor >= 0),
  currency public.currency_code not null,
  per text not null check (per in ('person','room_night','person_night','booking')),
  valid_from date not null,
  valid_to date not null,
  active boolean not null default true
);
create trigger set_updated_at before update on public.umrah_inventory for each row execute function public.set_updated_at();
alter table public.umrah_inventory enable row level security;
alter table public.umrah_inventory force row level security;
revoke insert, update, delete, truncate on public.umrah_inventory from anon, authenticated;
grant select on public.umrah_inventory to authenticated;
create policy umrah_inventory_read on public.umrah_inventory for select using (public.is_staff());
