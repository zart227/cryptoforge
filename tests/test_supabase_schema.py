from pathlib import Path


MIGRATION = Path("supabase/migrations/20260925000100_initial_schema.sql")


EXPECTED_TABLES = {
    "strategies",
    "strategy_versions",
    "trades",
    "trade_features",
    "experiments",
    "backtest_runs",
    "walk_forward_runs",
    "model_runs",
    "model_metrics",
    "daily_metrics",
    "system_events",
}


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_supabase_migration_contains_expected_tables() -> None:
    sql = _sql()

    for table in EXPECTED_TABLES:
        assert f"create table public.{table}" in sql


def test_supabase_migration_enables_rls_and_revokes_client_roles() -> None:
    sql = _sql()

    for table in EXPECTED_TABLES:
        assert f"alter table public.{table} enable row level security" in sql
        assert f"'{table}'" in sql

    assert "revoke all on public.%i from %i" in sql
    assert "'anon'" in sql
    assert "'authenticated'" in sql


def test_supabase_migration_uses_uuid_primary_keys() -> None:
    sql = _sql()

    assert "create extension if not exists pgcrypto" in sql
    assert sql.count("id uuid primary key default gen_random_uuid()") >= len(
        EXPECTED_TABLES
    )


def test_supabase_migration_excludes_bulk_or_binary_storage() -> None:
    sql = _sql()

    assert " bytea" not in sql
    assert "create table public.raw_candles" not in sql
    assert "create table public.ticks" not in sql
    assert "create table public.order_book" not in sql
    assert "artifact_sha256" in sql
    assert "artifact_uri" in sql
