from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from cryptoforge.backtesting import BacktestSpec, find_obvious_future_leakage


class QuantSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class QuantFinding:
    area: str
    severity: QuantSeverity
    message: str


@dataclass(frozen=True)
class BacktestEvidence:
    trade_count: int
    fee: Decimal
    timerange: str
    chronological_split_defined: bool
    out_of_sample_defined: bool
    walk_forward_defined: bool


@dataclass(frozen=True)
class QuantAuditReport:
    findings: tuple[QuantFinding, ...]

    @property
    def blocking_findings(self) -> tuple[QuantFinding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == QuantSeverity.BLOCKING)

    @property
    def can_claim_strategy_validity(self) -> bool:
        return not self.blocking_findings


def audit_strategy(
    *,
    strategy_path: str | Path,
    config_path: str | Path,
    backtest_spec: BacktestSpec,
    evidence: BacktestEvidence,
    minimum_trade_count: int = 30,
) -> QuantAuditReport:
    findings: list[QuantFinding] = []

    strategy = Path(strategy_path)
    config_file = Path(config_path)
    leakage_findings = find_obvious_future_leakage(strategy)
    if leakage_findings:
        findings.extend(
            QuantFinding("lookahead/data_leakage", QuantSeverity.BLOCKING, finding)
            for finding in leakage_findings
        )
    else:
        findings.append(
            QuantFinding(
                "lookahead/data_leakage",
                QuantSeverity.INFO,
                "No obvious negative shift, centered rolling, or direct .iloc[-1] leakage patterns found.",
            )
        )

    config = json.loads(config_file.read_text(encoding="utf-8"))
    if config.get("dry_run") is not True:
        findings.append(QuantFinding("execution_mode", QuantSeverity.BLOCKING, "Backtest config is not dry-run."))
    if config.get("trading_mode") != "spot":
        findings.append(QuantFinding("execution_mode", QuantSeverity.BLOCKING, "Backtest config is not Spot."))
    if config.get("margin_mode") not in ("", None):
        findings.append(QuantFinding("execution_mode", QuantSeverity.BLOCKING, "Margin mode is enabled."))

    if evidence.fee <= 0:
        findings.append(QuantFinding("fees", QuantSeverity.BLOCKING, "Backtest fee must be positive."))
    else:
        findings.append(QuantFinding("fees", QuantSeverity.INFO, f"Fee included: {evidence.fee}."))

    if "order_book_top" in json.dumps(config):
        findings.append(
            QuantFinding(
                "fills/spread",
                QuantSeverity.WARNING,
                "Order-book pricing is configured, but historical fill/spread realism still requires live paper evidence.",
            )
        )
    else:
        findings.append(
            QuantFinding(
                "fills/spread",
                QuantSeverity.WARNING,
                "Spread and fill realism are not proven by this bounded backtest.",
            )
        )

    if Decimal(str(backtest_spec.stake_amount)) < Decimal("5"):
        findings.append(
            QuantFinding("minimum_order_size", QuantSeverity.BLOCKING, "Stake amount is below assumed minimum order notional.")
        )
    else:
        findings.append(QuantFinding("minimum_order_size", QuantSeverity.INFO, "Stake amount is above assumed minimum."))

    if evidence.trade_count < minimum_trade_count:
        findings.append(
            QuantFinding(
                "insufficient_trade_count",
                QuantSeverity.BLOCKING,
                f"Only {evidence.trade_count} trades observed; require at least {minimum_trade_count} before validity claims.",
            )
        )

    if len(backtest_spec.pairs) == 1:
        findings.append(
            QuantFinding(
                "selection_bias",
                QuantSeverity.WARNING,
                "Single-pair BTC/USDT baseline is useful as a control but does not remove selection bias.",
            )
        )

    if not evidence.chronological_split_defined:
        findings.append(
            QuantFinding("chronological_split", QuantSeverity.BLOCKING, "Chronological split is not defined.")
        )
    if not evidence.out_of_sample_defined:
        findings.append(
            QuantFinding("out_of_sample", QuantSeverity.BLOCKING, "Out-of-sample separation is not defined.")
        )
    if not evidence.walk_forward_defined:
        findings.append(
            QuantFinding("walk_forward", QuantSeverity.BLOCKING, "Walk-forward methodology is not defined.")
        )

    return QuantAuditReport(tuple(findings))
