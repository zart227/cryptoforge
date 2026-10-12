"""Outcome-only price-path bounds; OHLC cannot resolve order inside an exit bar."""
from decimal import Decimal

RISK_TARGET_VERSION = 'spot-long-ohlc-excursion-bounds-v1'


def trade_risk_outcome(trade, candles, config):
    lookup = {row.open_time: index for index,row in enumerate(candles)}
    entry, exit_ = lookup[trade.entry_time], lookup[trade.exit_time]
    if exit_ < entry or len(candles) < 2:
        raise ValueError('ordered complete trade path required')
    step = candles[1].open_time-candles[0].open_time
    # Gap/timeout exits happen at the open. Intrabar exit prices are touched,
    # but that candle's remaining extremes may happen after the position closes.
    opening_exit = trade.exit_reason in {'stop_gap','target_gap','timeout'}
    closing_exit = trade.exit_reason == 'end_of_data'
    intrabar_exit = trade.exit_reason in {'stop','target'}
    if not (opening_exit or closing_exit or intrabar_exit):
        raise ValueError('unsupported trade exit timing')
    full = candles[entry:exit_+1] if closing_exit else candles[entry:exit_]
    raw_exit = trade.exit_price/(1-config.slippage)
    bid_factor=1-config.spread_fraction/2
    observed = [trade.entry_price, raw_exit, candles[exit_].open*bid_factor]
    lows = observed+[row.low*bid_factor for row in full]
    highs = observed+[row.high*bid_factor for row in full]
    possible_lows = lows+[candles[exit_].low*bid_factor] if intrabar_exit else lows
    possible_highs = highs+[candles[exit_].high*bid_factor] if intrabar_exit else highs
    zero = Decimal(0)
    duration = (trade.exit_time-trade.entry_time).total_seconds()
    if closing_exit:duration += step.total_seconds()
    return {'risk_target_version':RISK_TARGET_VERSION,
            'maximum_adverse_price_fraction_lower_bound': max(zero,1-min(lows)/trade.entry_price),
            'maximum_adverse_price_fraction_upper_bound': max(zero,1-min(possible_lows)/trade.entry_price),
            'maximum_favorable_price_fraction_lower_bound': max(zero,max(highs)/trade.entry_price-1),
            'maximum_favorable_price_fraction_upper_bound': max(zero,max(possible_highs)/trade.entry_price-1),
            'holding_seconds_lower_bound': duration,
            'holding_seconds_upper_bound': duration+step.total_seconds() if intrabar_exit else duration,
            'outcome_available_at': trade.exit_time+step,
            'exit_bar_order_unknown': intrabar_exit,
            'price_bounds_include_fees': False,
            'scope':'independent_simulated_trade_outcome_not_entry_features_or_portfolio_drawdown',
            'live_profitability_established':False}
