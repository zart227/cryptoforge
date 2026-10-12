"""Select a declared threshold grid from validation portfolio summaries only.

This consumes execution-simulator results, not per-bar predicted returns. The
caller must register every grid trial and verify referenced report checksums.
Selection alone never qualifies a model for test, paper, or live trading.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re


def _number(value):
    if isinstance(value, bool):
        raise ValueError('finite numeric metric required')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('finite numeric metric required')
    return result


@dataclass(frozen=True)
class ValidationPortfolio:
    threshold: Decimal
    role: str
    start: datetime
    end: datetime
    study_sha256: str
    report_sha256: str
    initial_cash: Decimal
    net_pnl: Decimal
    stress_net_pnl: Decimal
    max_drawdown: Decimal
    stress_max_drawdown: Decimal
    trade_count: int
    stress_trade_count: int


def select_validation_threshold(results, *, declared_thresholds, validation_start,
                                validation_end, study_sha256, minimum_trades,
                                maximum_drawdown):
    """Rank eligible trials by stress return, then net return, then threshold.

    All trials must share capital and the exact declared validation period.
    Nonpositive net/stress return and insufficient activity yield no candidate.
    """
    for timestamp in (validation_start, validation_end):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError('aware validation boundaries required')
    if validation_start >= validation_end:
        raise ValueError('ordered validation boundaries required')
    if not re.fullmatch('[0-9a-f]{64}', study_sha256):
        raise ValueError('study SHA256 required')
    if type(minimum_trades) is not int or minimum_trades < 1:
        raise ValueError('positive minimum trade count required')
    limit = _number(maximum_drawdown)
    if not 0 < limit <= 1:
        raise ValueError('drawdown bound must be in (0,1]')
    grid = tuple(_number(value) for value in declared_thresholds)
    if not grid or len(set(grid)) != len(grid) or any(not 0 <= value <= 1 for value in grid):
        raise ValueError('explicit unique probability threshold grid required')
    trials = {}
    capital = None
    eligible = []
    for result in results:
        threshold = _number(result.threshold)
        if threshold not in grid or threshold in trials:
            raise ValueError('undeclared or duplicate threshold trial')
        if (result.role != 'validation' or result.start != validation_start
                or result.end != validation_end or result.study_sha256 != study_sha256):
            raise ValueError('trial must match validation scope and study')
        if not re.fullmatch('[0-9a-f]{64}', result.report_sha256):
            raise ValueError('referenced report SHA256 required')
        cash, net, stress, drawdown = map(_number, (result.initial_cash,
            result.net_pnl, result.stress_net_pnl, result.max_drawdown))
        if cash <= 0 or not 0 <= drawdown <= 1 or net < -cash or stress < -cash:
            raise ValueError('invalid Spot portfolio metrics')
        stress_drawdown = _number(result.stress_max_drawdown)
        if not 0 <= stress_drawdown <= 1:
            raise ValueError('invalid stress drawdown')
        if capital is not None and capital != cash:
            raise ValueError('same initial capital required across trials')
        capital = cash
        if any(type(count) is not int or count < 0 for count in (result.trade_count,result.stress_trade_count)):
            raise ValueError('nonnegative integer trade count required')
        trials[threshold] = result
        if (min(result.trade_count,result.stress_trade_count) >= minimum_trades and net > 0 and stress > 0
                and max(drawdown, stress_drawdown) <= limit):
            eligible.append((stress / cash, net / cash, threshold, result.report_sha256))
    if set(trials) != set(grid):
        raise ValueError('complete declared threshold grid required')
    winner = max(eligible) if eligible else None
    return {'selected_threshold': str(winner[2]) if winner else None,
            'selected_report_sha256': winner[3] if winner else None,
            'tested_thresholds': len(trials), 'eligible_thresholds': len(eligible),
            'selection_role': 'validation', 'ranking': 'stress_return_then_net_return_then_higher_threshold',
            'independent_profitability_established': False, 'live_promotion_allowed': False,
            'report_checksums_verified_by_selector': False}
