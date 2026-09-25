import ast
import json
from pathlib import Path


STRATEGY = Path("user_data/strategies/CryptoForgeBaselineStrategy.py")
METADATA = Path("config/baseline_strategy_metadata.json")
CONFIG = Path("config/freqtrade.baseline-dry-run.json")


def test_baseline_strategy_has_expected_metadata() -> None:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert metadata["strategy_name"] == "CryptoForgeBaselineStrategy"
    assert metadata["version"] == "cryptoforge-baseline-v0.1.0"
    assert metadata["status"] == "BACKTESTED"
    assert config["dry_run"] is True
    assert config["trading_mode"] == "spot"
    assert config["margin_mode"] == ""
    assert config["exchange"]["name"] == "bybit"
    assert config["exchange"]["key"] == ""
    assert config["exchange"]["secret"] == ""
    assert config["strategy"] == "CryptoForgeBaselineStrategy"


def test_baseline_strategy_does_not_use_obvious_future_leakage_patterns() -> None:
    source = STRATEGY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_literals = {-1, -2, -3}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "shift":
                for arg in node.args:
                    if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                        assert not (
                            isinstance(arg.operand, ast.Constant)
                            and arg.operand.value in {1, 2, 3}
                        )
                    if isinstance(arg, ast.Constant):
                        assert arg.value not in forbidden_literals
            if node.func.attr == "rolling":
                for keyword in node.keywords:
                    assert not (
                        keyword.arg == "center"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    )

    assert ".iloc[-1]" not in source
    assert "lookahead" not in source.lower()


def test_baseline_strategy_documents_entry_and_exit_tags() -> None:
    source = STRATEGY.read_text(encoding="utf-8")
    docs = Path("docs/BASELINE_STRATEGY.md").read_text(encoding="utf-8")

    assert "ema_rsi_volume_atr_baseline" in source
    assert "baseline_exit_signal" in source
    assert "ema_rsi_volume_atr_baseline" in docs
    assert "baseline_exit_signal" in docs
