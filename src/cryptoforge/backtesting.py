from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BacktestSpec:
    config_path: str
    userdir: str
    datadir: str
    strategy_path: str
    strategy: str
    pairs: tuple[str, ...]
    timeframe: str
    timerange: str
    fee: str
    max_open_trades: int
    stake_amount: str
    dry_run_wallet: str
    export: str = "none"
    cache: str = "none"
    data_format_ohlcv: str = "feather"

    def validate(self) -> None:
        if not self.pairs:
            raise ValueError("at least one pair is required")
        if self.export != "none":
            raise ValueError("baseline backtests should save summaries, not unlimited exports")
        if self.cache != "none":
            raise ValueError("cache must be none for reproducible baseline verification")
        if self.max_open_trades < 1:
            raise ValueError("max_open_trades must be positive")
        if not self.timerange or "-" not in self.timerange:
            raise ValueError("bounded timerange is required")

    def download_command(self, freqtrade_bin: str) -> list[str]:
        self.validate()
        return [
            freqtrade_bin,
            "download-data",
            "-c",
            self.config_path,
            "--userdir",
            self.userdir,
            "--datadir",
            self.datadir,
            "--pairs",
            *self.pairs,
            "--timeframes",
            self.timeframe,
            "--timerange",
            self.timerange,
            "--trading-mode",
            "spot",
            "--data-format-ohlcv",
            self.data_format_ohlcv,
            "--no-parallel-download",
        ]

    def backtest_command(self, freqtrade_bin: str) -> list[str]:
        self.validate()
        return [
            freqtrade_bin,
            "backtesting",
            "-c",
            self.config_path,
            "--userdir",
            self.userdir,
            "--datadir",
            self.datadir,
            "--strategy-path",
            self.strategy_path,
            "--strategy",
            self.strategy,
            "--pairs",
            *self.pairs,
            "--timeframe",
            self.timeframe,
            "--timerange",
            self.timerange,
            "--fee",
            self.fee,
            "--max-open-trades",
            str(self.max_open_trades),
            "--stake-amount",
            self.stake_amount,
            "--dry-run-wallet",
            self.dry_run_wallet,
            "--export",
            self.export,
            "--cache",
            self.cache,
        ]

    def low_priority_shell_command(self, command: list[str]) -> str:
        escaped = " ".join(shell_quote(part) for part in command)
        return f"nice -n 10 ionice -c2 -n7 {escaped}"


def baseline_backtest_spec() -> BacktestSpec:
    return BacktestSpec(
        config_path="/opt/cryptoforge/config/freqtrade.baseline-dry-run.json",
        userdir="/opt/cryptoforge/user_data",
        datadir="/opt/cryptoforge/data",
        strategy_path="/opt/cryptoforge/user_data/strategies",
        strategy="CryptoForgeBaselineStrategy",
        pairs=("BTC/USDT",),
        timeframe="5m",
        timerange="20260923-20260925",
        fee="0.001",
        max_open_trades=2,
        stake_amount="10",
        dry_run_wallet="1000",
    )


def find_obvious_future_leakage(strategy_path: str | Path) -> list[str]:
    source = Path(strategy_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "shift":
                for arg in node.args:
                    if is_negative_numeric_literal(arg):
                        findings.append("negative shift() can introduce future leakage")
            if node.func.attr == "rolling":
                for keyword in node.keywords:
                    if (
                        keyword.arg == "center"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ):
                        findings.append("center=True rolling window can introduce future leakage")

    if ".iloc[-1]" in source:
        findings.append("direct .iloc[-1] usage can hide full-dataframe leakage")
    return sorted(set(findings))


def is_negative_numeric_literal(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    )


def shell_quote(value: str) -> str:
    if not value:
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/:.=+-"
    if all(char in safe for char in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
