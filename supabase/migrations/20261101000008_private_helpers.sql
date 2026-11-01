-- Move RLS helper functions out of the API-exposed `public` schema (Supabase advisor 0028/0029):
-- policies keep working (they reference functions by oid) but /rest/v1/rpc/* can no longer call them.
create schema if not exists private;
grant usage on schema private to anon, authenticated;

alter function public.app_role() set schema private;
alter function public.is_staff() set schema private;
alter function public.my_partner_id() set schema private;
alter function public.owns_case(uuid) set schema private;
alter function public.partner_case(uuid) set schema private;
alter function public.can_read_case(uuid) set schema private;

create or replace function private.app_role() returns text
language sql stable security definer set search_path = '' as $$
  select coalesce((select role from public.profiles where id = auth.uid()), 'anon')
$$;
create or replace function private.is_staff() returns boolean
language sql stable security definer set search_path = '' as $$
  select private.app_role() in ('ops','admin')
$$;
create or replace function private.my_partner_id() returns uuid
language sql stable security definer set search_path = '' as $$
  select partner_id from public.profiles where id = auth.uid() and role = 'partner'
$$;
create or replace function private.owns_case(p_case uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.cases where id = p_case and owner_id = auth.uid())
$$;
create or replace function private.partner_case(p_case uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.cases
                 where id = p_case and partner_id is not null and partner_id = private.my_partner_id())
$$;
create or replace function private.can_read_case(p_case uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select private.owns_case(p_case) or private.is_staff() or private.partner_case(p_case)
$$;

revoke execute on all functions in schema private from public;
grant execute on all functions in schema private to anon, authenticated;

-- trigger-only function: nobody needs to call it directly
revoke execute on function public.handle_new_user() from public, anon, authenticated;
alter function public.set_updated_at() set search_path = '';
