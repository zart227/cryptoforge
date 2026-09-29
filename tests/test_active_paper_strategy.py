import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

sys.path.insert(0, str(Path('user_data/strategies').resolve()))
from CryptoForgeBaselineStrategy import CryptoForgeBaselineStrategy
from CryptoForgeActivePaperStrategy import CryptoForgeActivePaperStrategy
from CryptoForgeSmallBalancePilotStrategy import CryptoForgeSmallBalancePilotStrategy
from freqtrade.exceptions import OperationalException


def test_breakout_enters_without_conflicting_exit():
    frame = pd.DataFrame([dict(close=102, open=100, resistance=101,
        ema_fast=101, ema_slow=99, rsi=60, support_bounce=False,
        resistance_breakout=True, volume_ratio=1.5, atr_pct=.01,
        volume=100, near_resistance=True, support_breakdown=False)])
    strategy = CryptoForgeBaselineStrategy({})
    result = strategy.populate_exit_trend(strategy.populate_entry_trend(frame, {}), {})
    assert result.iloc[0].enter_long == 1
    assert result.iloc[0].exit_long == 0
    frame.loc[0, ['close', 'open']] = [100, 101]
    assert strategy.populate_exit_trend(frame, {}).iloc[0].exit_long == 1


def test_paper_universe_cannot_enable_live_trading():
    strategy = CryptoForgeActivePaperStrategy({'dry_run': False})
    with pytest.raises(OperationalException):
        strategy.bot_start()
    assert not strategy.entry_pair_allowed('SOL/USDT')
    strategy.config['dry_run'] = True
    strategy.dp = Mock()
    strategy.dp.current_whitelist.return_value = ['SOL/USDT']
    assert strategy.entry_pair_allowed('SOL/USDT')
    assert not strategy.entry_pair_allowed('BTC/USDT')
    assert not CryptoForgeSmallBalancePilotStrategy({}).entry_pair_allowed('SOL/USDT')
