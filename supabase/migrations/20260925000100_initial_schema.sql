-- CryptoForge durable state schema.
-- This migration intentionally stores summaries, identifiers, metrics and
-- artifact metadata. Reproducible bulk market data and model binaries belong
-- outside PostgreSQL unless a later audited migration justifies otherwise.

create extension if not exists pgcrypto;

create schema if not exists internal;

create or replace function internal.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

revoke all on all functions in schema internal from public;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on schema internal from anon;
    end if;

    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on schema internal from authenticated;
    end if;
end;
$$;

create table public.strategies (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    family text not null,
    description text,
    status text not null default 'DRAFT' check (
        status in (
            'DRAFT',
            'BACKTESTED',
            'OUT_OF_SAMPLE_TESTED',
            'WALK_FORWARD_TESTED',
            'PAPER_TRADING',
            'CANDIDATE',
            'APPROVED',
            'RETIRED',
            'REJECTED'
        )
    ),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.strategy_versions (
    id uuid primary key default gen_random_uuid(),
    strategy_id uuid not null references public.strategies(id) on delete cascade,
    version text not null,
    source_hash text not null,
    parameters jsonb not null default '{}'::jsonb,
    risk_profile jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (strategy_id, version)
);

create table public.experiments (
    id uuid primary key default gen_random_uuid(),
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    name text not null,
    kind text not null check (
        kind in (
            'backtest',
            'walk_forward',
            'model',
            'parameter_search',
            'research'
        )
    ),
    status text not null default 'planned' check (
        status in ('planned', 'running', 'completed', 'failed', 'cancelled')
    ),
    dataset_ref text,
    config_hash text,
    parameters jsonb not null default '{}'::jsonb,
    result_summary jsonb not null default '{}'::jsonb,
    artifact_uri text,
    artifact_sha256 text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.trades (
    id uuid primary key default gen_random_uuid(),
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    external_trade_id text,
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type = 'spot'),
    mode text not null default 'dry_run' check (mode in ('dry_run', 'live')),
    pair text not null,
    timeframe text not null,
    side text not null default 'long' check (side = 'long'),
    status text not null default 'open' check (
        status in ('open', 'closed', 'cancelled', 'error')
    ),
    opened_at timestamptz not null,
    closed_at timestamptz,
    entry_price numeric(28, 12),
    exit_price numeric(28, 12),
    amount numeric(28, 12),
    stake_amount numeric(28, 12),
    fee_amount numeric(28, 12),
    realized_pnl numeric(28, 12),
    realized_pnl_pct numeric(18, 8),
    stop_loss numeric(28, 12),
    take_profit numeric(28, 12),
    regime text,
    entry_reason text,
    exit_reason text,
    idempotency_key text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (external_trade_id)
);

create table public.trade_features (
    id uuid primary key default gen_random_uuid(),
    trade_id uuid not null references public.trades(id) on delete cascade,
    captured_at timestamptz not null,
    features jsonb not null default '{}'::jsonb,
    market_snapshot jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (trade_id, captured_at)
);

create table public.backtest_runs (
    id uuid primary key default gen_random_uuid(),
    experiment_id uuid references public.experiments(id) on delete cascade,
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    timeframe text not null,
    started_at timestamptz not null,
    ended_at timestamptz not null,
    fee_model jsonb not null default '{}'::jsonb,
    metrics jsonb not null default '{}'::jsonb,
    summary_only boolean not null default true,
    created_at timestamptz not null default now()
);

create table public.walk_forward_runs (
    id uuid primary key default gen_random_uuid(),
    experiment_id uuid references public.experiments(id) on delete cascade,
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    windows jsonb not null default '[]'::jsonb,
    metrics jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table public.model_runs (
    id uuid primary key default gen_random_uuid(),
    experiment_id uuid references public.experiments(id) on delete set null,
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    model_family text not null,
    feature_version text not null,
    train_range tstzrange,
    validation_range tstzrange,
    test_range tstzrange,
    artifact_uri text,
    artifact_sha256 text,
    metrics jsonb not null default '{}'::jsonb,
    status text not null default 'planned' check (
        status in ('planned', 'running', 'completed', 'failed', 'rejected')
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.model_metrics (
    id uuid primary key default gen_random_uuid(),
    model_run_id uuid not null references public.model_runs(id) on delete cascade,
    split text not null check (split in ('train', 'validation', 'test', 'paper')),
    metric_name text not null,
    metric_value numeric(28, 12) not null,
    created_at timestamptz not null default now(),
    unique (model_run_id, split, metric_name)
);

create table public.daily_metrics (
    id uuid primary key default gen_random_uuid(),
    metric_date date not null,
    strategy_version_id uuid references public.strategy_versions(id) on delete set null,
    mode text not null default 'dry_run' check (mode in ('dry_run', 'live')),
    net_pnl numeric(28, 12),
    gross_profit numeric(28, 12),
    gross_loss numeric(28, 12),
    fees numeric(28, 12),
    trade_count integer not null default 0 check (trade_count >= 0),
    win_rate numeric(12, 8),
    profit_factor numeric(18, 8),
    expectancy numeric(28, 12),
    max_drawdown numeric(18, 8),
    sharpe numeric(18, 8),
    sortino numeric(18, 8),
    metrics jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (metric_date, strategy_version_id, mode)
);

create table public.system_events (
    id uuid primary key default gen_random_uuid(),
    occurred_at timestamptz not null,
    source text not null,
    severity text not null check (
        severity in ('debug', 'info', 'warning', 'error', 'critical')
    ),
    event_type text not null,
    idempotency_key text unique,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index strategies_status_idx on public.strategies (status);
create index strategy_versions_strategy_id_idx on public.strategy_versions (strategy_id);
create index experiments_status_idx on public.experiments (status);
create index experiments_strategy_version_id_idx on public.experiments (strategy_version_id);
create index trades_strategy_version_id_idx on public.trades (strategy_version_id);
create index trades_pair_opened_at_idx on public.trades (pair, opened_at desc);
create index trades_mode_status_idx on public.trades (mode, status);
create index trade_features_trade_id_idx on public.trade_features (trade_id);
create index backtest_runs_strategy_version_id_idx on public.backtest_runs (strategy_version_id);
create index walk_forward_runs_strategy_version_id_idx on public.walk_forward_runs (strategy_version_id);
create index model_runs_strategy_version_id_idx on public.model_runs (strategy_version_id);
create index model_runs_status_idx on public.model_runs (status);
create index model_metrics_model_run_id_idx on public.model_metrics (model_run_id);
create index daily_metrics_metric_date_idx on public.daily_metrics (metric_date desc);
create index system_events_occurred_at_idx on public.system_events (occurred_at desc);
create index system_events_severity_idx on public.system_events (severity);

create trigger strategies_set_updated_at
before update on public.strategies
for each row execute function internal.set_updated_at();

create trigger strategy_versions_set_updated_at
before update on public.strategy_versions
for each row execute function internal.set_updated_at();

create trigger experiments_set_updated_at
before update on public.experiments
for each row execute function internal.set_updated_at();

create trigger trades_set_updated_at
before update on public.trades
for each row execute function internal.set_updated_at();

create trigger model_runs_set_updated_at
before update on public.model_runs
for each row execute function internal.set_updated_at();

create trigger daily_metrics_set_updated_at
before update on public.daily_metrics
for each row execute function internal.set_updated_at();

alter table public.strategies enable row level security;
alter table public.strategy_versions enable row level security;
alter table public.experiments enable row level security;
alter table public.trades enable row level security;
alter table public.trade_features enable row level security;
alter table public.backtest_runs enable row level security;
alter table public.walk_forward_runs enable row level security;
alter table public.model_runs enable row level security;
alter table public.model_metrics enable row level security;
alter table public.daily_metrics enable row level security;
alter table public.system_events enable row level security;

do $$
declare
    role_name text;
    table_name text;
begin
    foreach role_name in array array['anon', 'authenticated']
    loop
        if exists (select 1 from pg_roles where rolname = role_name) then
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
                    'revoke all on public.%I from %I',
                    table_name,
                    role_name
                );
            end loop;
        end if;
    end loop;
end;
$$;

comment on table public.trades is
    'Durable trade journal for dry-run and future audited live spot trades.';
comment on table public.trade_features is
    'Compact feature snapshots captured around a trade, not bulk candle storage.';
comment on table public.experiments is
    'Research, backtest, walk-forward and model experiment metadata.';
comment on table public.model_runs is
    'Model training metadata and artifact references; binaries stay in object storage.';
comment on table public.system_events is
    'Auditable operational events delivered through the local outbox.';
