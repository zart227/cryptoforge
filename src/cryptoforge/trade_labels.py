"""Spot-long trade-outcome targets using exactly the offline simulator rules."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from cryptoforge.model_training import TrainingExample, build_examples
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.trade_simulator import SimulationConfig, SimulatedTrade, simulate_portfolio
from cryptoforge.trade_risk_labels import trade_risk_outcome

TARGET_VERSION = 'spot-long-trade-net-v2'


@dataclass(frozen=True)
class TradeLabel:
    pair: str
    signal_time: datetime
    status: str
    label_end_time: datetime
    example: TrainingExample | None
    trade: SimulatedTrade | None
    net_return: float | None
    rejection_reason: str | None = None
    risk_outcome: dict | None = None


def build_trade_labels(pair: str, candles: Sequence[CandleRow],
                       config: SimulationConfig = SimulationConfig()) -> list[TradeLabel]:
    """Counterfactual independent entries, NOT simultaneous portfolio trades.

    Each candidate uses fixed ex-ante stops/targets/hold rules. Only complete
    horizons are labeled. Refused executions are not negative training examples.
    short_label is a compatibility placeholder and must not train a short head.
    """
    if len(candles) < 2:
        return []
    # Validate the complete history before constructing horizons across it.
    simulate_portfolio({pair:candles},{},config)
    step=candles[1].open_time-candles[0].open_time
    horizon=config.entry_delay_bars+config.hold_bars
    features=build_examples(pair,list(candles),horizon_candles=horizon)
    indices={c.open_time:i for i,c in enumerate(candles)}
    labels=[]
    for feature in features:
        index=indices[feature.open_time]
        window=candles[index:index+horizon+1]
        result=simulate_portfolio({pair:window},{pair:[feature.open_time]},config)
        if not result.trades:
            labels.append(TradeLabel(pair,feature.open_time,'rejected',window[-1].open_time+step,
                                    None,None,None,result.rejections[0]['reason']))
            continue
        trade=result.trades[0]
        if trade.exit_reason=='end_of_data':
            raise ValueError('incomplete horizon must not become a trade label')
        # Exit candle OHLC was consumed: labels are available only after its close.
        end=trade.exit_time+step
        net=float(trade.net_pnl/trade.cost)
        example=replace(feature,label=int(trade.net_pnl>Decimal(0)),short_label=0,
                        future_return=net,label_end_time=end)
        labels.append(TradeLabel(pair,feature.open_time,'executed',end,example,trade,net,
                                risk_outcome=trade_risk_outcome(trade,window,config)))
    return labels
