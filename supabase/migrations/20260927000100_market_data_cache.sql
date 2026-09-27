-- Market-data cache and decision journal for server-side trading agents.
-- This stores bounded OHLCV/ticker snapshots and compact decision records.
-- It intentionally does not store raw tick streams, full order books or secrets.

create table if not exists public.market_candles (
    id uuid primary key default gen_random_uuid(),
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type in ('spot', 'linear', 'inverse')),
    symbol text not null,
    pair text not null,
    timeframe text not null,
    open_time timestamptz not null,
    close_time timestamptz not null,
    open numeric(28, 12) not null,
    high numeric(28, 12) not null,
    low numeric(28, 12) not null,
    close numeric(28, 12) not null,
    volume numeric(36, 12) not null,
    turnover numeric(36, 12) not null,
    source text not null default 'bybit_public_api',
    ingested_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (exchange, market_type, symbol, timeframe, open_time)
);

create table if not exists public.market_tickers (
    id uuid primary key default gen_random_uuid(),
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type in ('spot', 'linear', 'inverse')),
    symbol text not null,
    pair text not null,
    last_price numeric(28, 12) not null,
    bid_price numeric(28, 12),
    ask_price numeric(28, 12),
    high_price_24h numeric(28, 12),
    low_price_24h numeric(28, 12),
    turnover_24h numeric(36, 12),
    volume_24h numeric(36, 12),
    observed_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (exchange, market_type, symbol)
);

create table if not exists public.selected_universe (
    id uuid primary key default gen_random_uuid(),
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type in ('spot', 'linear', 'inverse')),
    selection_name text not null default 'live-pilot',
    selected_at timestamptz not null default now(),
    pairs jsonb not null default '[]'::jsonb,
    scanner_config jsonb not null default '{}'::jsonb,
    selected jsonb not null default '[]'::jsonb,
    rejected_count integer not null default 0 check (rejected_count >= 0),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.strategy_signals (
    id uuid primary key default gen_random_uuid(),
    signal_at timestamptz not null,
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type in ('spot', 'linear', 'inverse')),
    pair text not null,
    timeframe text not null,
    strategy_name text not null,
    strategy_version text not null,
    signal text not null check (
        signal in ('enter_long', 'exit_long', 'hold', 'no_new_entry', 'reject')
    ),
    confidence numeric(12, 8),
    source_candle_open_time timestamptz,
    features jsonb not null default '{}'::jsonb,
    reasons jsonb not null default '[]'::jsonb,
    idempotency_key text not null unique,
    created_at timestamptz not null default now()
);

create table if not exists public.trade_decisions (
    id uuid primary key default gen_random_uuid(),
    decided_at timestamptz not null,
    exchange text not null default 'bybit' check (exchange = 'bybit'),
    market_type text not null default 'spot' check (market_type in ('spot', 'linear', 'inverse')),
    mode text not null check (mode in ('dry_run', 'live', 'shadow')),
    pair text not null,
    timeframe text not null,
    strategy_name text not null,
    strategy_version text not null,
    decision text not null check (
        decision in ('approve_entry', 'reject_entry', 'approve_exit', 'hold', 'no_new_trades')
    ),
    risk_decision text,
    stake_amount numeric(28, 12),
    reference_price numeric(28, 12),
    signal_id uuid references public.strategy_signals(id) on delete set null,
    features jsonb not null default '{}'::jsonb,
    reasons jsonb not null default '[]'::jsonb,
    idempotency_key text not null unique,
    created_at timestamptz not null default now()
);

create table if not exists public.bot_health (
    id uuid primary key default gen_random_uuid(),
    observed_at timestamptz not null default now(),
    component text not null,
    status text not null check (status in ('ok', 'warning', 'error', 'critical')),
    message text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (component)
);

create index if not exists market_candles_pair_time_idx
    on public.market_candles (pair, timeframe, open_time desc);
create index if not exists market_candles_symbol_time_idx
    on public.market_candles (symbol, timeframe, open_time desc);
create index if not exists market_tickers_observed_at_idx
    on public.market_tickers (observed_at desc);
create index if not exists selected_universe_active_idx
    on public.selected_universe (selection_name, is_active, selected_at desc);
create index if not exists strategy_signals_pair_time_idx
    on public.strategy_signals (pair, timeframe, signal_at desc);
create index if not exists trade_decisions_pair_time_idx
    on public.trade_decisions (pair, timeframe, decided_at desc);
create index if not exists bot_health_status_idx
    on public.bot_health (status, observed_at desc);

create trigger market_candles_set_updated_at
before update on public.market_candles
for each row execute function internal.set_updated_at();

create trigger market_tickers_set_updated_at
before update on public.market_tickers
for each row execute function internal.set_updated_at();

create trigger selected_universe_set_updated_at
before update on public.selected_universe
for each row execute function internal.set_updated_at();

alter table public.market_candles enable row level security;
alter table public.market_tickers enable row level security;
alter table public.selected_universe enable row level security;
alter table public.strategy_signals enable row level security;
alter table public.trade_decisions enable row level security;
alter table public.bot_health enable row level security;

do $$
declare
    role_name text;
    table_name text;
begin
    foreach role_name in array array['anon', 'authenticated']
    loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            foreach table_name in array array[
                'market_candles',
                'market_tickers',
                'selected_universe',
                'strategy_signals',
                'trade_decisions',
                'bot_health'
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

do $$
declare
    table_name text;
begin
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        foreach table_name in array array[
            'market_candles',
            'market_tickers',
            'selected_universe',
            'strategy_signals',
            'trade_decisions',
            'bot_health'
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

comment on table public.market_candles is
    'Bounded normalized OHLCV cache for strategy analysis; not a raw tick archive.';
comment on table public.market_tickers is
    'Latest normalized ticker snapshots used by scanners and dashboards.';
comment on table public.selected_universe is
    'Auditable scanner-selected trading universe snapshots.';
comment on table public.strategy_signals is
    'Compact strategy signal journal before risk and execution checks.';
comment on table public.trade_decisions is
    'Auditable decision journal; Bybit remains source of truth for execution.';
comment on table public.bot_health is
    'Latest health state for collectors, strategy services and trading runtime.';
