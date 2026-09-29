-- Keep Freqtrade's operational ORM tables isolated from CryptoForge's
-- canonical public.trades journal and outside the Supabase Data API schema.
create schema if not exists freqtrade authorization postgres;

revoke all on schema freqtrade from public;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on schema freqtrade from anon;
    end if;

    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on schema freqtrade from authenticated;
    end if;

    if exists (select 1 from pg_roles where rolname = 'service_role') then
        revoke all on schema freqtrade from service_role;
    end if;
end;
$$;

grant usage, create on schema freqtrade to postgres;
