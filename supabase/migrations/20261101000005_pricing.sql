-- FX rates (ops-maintained) and quote bindingness.
create table public.fx_rates (
  currency public.currency_code primary key,
  rate_to_pkr numeric(14,6) not null check (rate_to_pkr > 0),   -- 1 unit of currency in PKR
  source text not null,
  updated_at timestamptz not null default now()
);
alter table public.fx_rates enable row level security;
alter table public.fx_rates force row level security;
revoke insert, update, delete, truncate on public.fx_rates from anon, authenticated;
grant select on public.fx_rates to anon, authenticated;
create policy fx_public on public.fx_rates for select using (true);

-- A quote is binding only if every priced line comes from verified/fresh (<=7d) official data.
alter table public.quotes add column binding boolean not null default true;
alter table public.quotes add column collect_minor bigint not null default 0;  -- what Rahbar collects
alter table public.quote_line_items add column indicative boolean not null default false;
alter table public.quote_line_items add column quantity int not null default 1 check (quantity > 0);
alter table public.quote_line_items add column unit_amount_minor bigint;
