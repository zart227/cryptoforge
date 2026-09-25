-- Allow the server-side Supabase secret/service role to use the REST API.
-- Client roles remain revoked by the initial schema migration.

do $$
declare
    table_name text;
begin
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        foreach table_name in array array[
            'strategies',
            'strategy_versions',
            'experiments',
            'trades',
            'trade_features',
            'backtest_runs',
            'walk_forward_runs',
            'model_runs',
            'model_metrics',
            'daily_metrics',
            'system_events'
        ]
        loop
            execute format(
                'grant select, insert, update, delete on public.%I to service_role',
                table_name
            );
        end loop;
    end if;
end;
$$;
