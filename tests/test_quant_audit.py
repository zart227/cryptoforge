from datetime import UTC, datetime
from decimal import Decimal

from cryptoforge.backtesting import BacktestSpec, baseline_backtest_spec
from cryptoforge.quant_audit import (
    BacktestEvidence,
    QuantSeverity,
    audit_strategy,
)


def baseline_evidence(**overrides) -> BacktestEvidence:  # type: ignore[no-untyped-def]
    values = {
        "trade_count": 5,
        "fee": Decimal("0.001"),
        "timerange": "20260923-20260925",
        "chronological_split_defined": True,
        "out_of_sample_defined": True,
        "walk_forward_defined": True,
    }
    values.update(overrides)
    return BacktestEvidence(**values)


def test_baseline_quant_audit_blocks_validity_claims_until_trade_count_is_sufficient() -> None:
    report = audit_strategy(
        strategy_path="user_data/strategies/CryptoForgeBaselineStrategy.py",
        config_path="config/freqtrade.baseline-dry-run.json",
        backtest_spec=baseline_backtest_spec(),
        evidence=baseline_evidence(),
    )

    assert not report.can_claim_strategy_validity
    assert any(
        finding.area == "insufficient_trade_count"
        and finding.severity == QuantSeverity.BLOCKING
        for finding in report.findings
    )
    assert not any(
        finding.area == "lookahead/data_leakage"
        and finding.severity == QuantSeverity.BLOCKING
        for finding in report.findings
    )


def test_quant_audit_allows_validity_claim_only_when_blockers_are_clear() -> None:
    spec = baseline_backtest_spec()
    report = audit_strategy(
        strategy_path="user_data/strategies/CryptoForgeBaselineStrategy.py",
        config_path="config/freqtrade.baseline-dry-run.json",
        backtest_spec=BacktestSpec(
            config_path=spec.config_path,
            userdir=spec.userdir,
            datadir=spec.datadir,
            strategy_path=spec.strategy_path,
            strategy=spec.strategy,
            pairs=("BTC/USDT", "ETH/USDT"),
            timeframe=spec.timeframe,
            timerange=spec.timerange,
            fee=spec.fee,
            max_open_trades=spec.max_open_trades,
            stake_amount=spec.stake_amount,
            dry_run_wallet=spec.dry_run_wallet,
        ),
        evidence=baseline_evidence(trade_count=120),
    )

    assert report.can_claim_strategy_validity
    assert report.blocking_findings == ()


def test_quant_audit_flags_obvious_future_leakage(tmp_path) -> None:
    strategy = tmp_path / "LeakyStrategy.py"
    strategy.write_text(
        """
from pandas import DataFrame

def populate_indicators(dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe["future"] = dataframe["close"].shift(-1)
    dataframe["centered"] = dataframe["close"].rolling(10, center=True).mean()
    dataframe["last"] = dataframe["close"].iloc[-1]
    return dataframe
        """,
        encoding="utf-8",
    )

    report = audit_strategy(
        strategy_path=strategy,
        config_path="config/freqtrade.baseline-dry-run.json",
        backtest_spec=baseline_backtest_spec(),
        evidence=baseline_evidence(trade_count=100),
    )

    leakage = [
        finding
        for finding in report.findings
        if finding.area == "lookahead/data_leakage"
    ]
    assert len(leakage) == 3
    assert all(finding.severity == QuantSeverity.BLOCKING for finding in leakage)
