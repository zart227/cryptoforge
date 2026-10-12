"""Deterministic offline Spot portfolio simulator; never submits exchange orders."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Mapping, Sequence

from cryptoforge.supabase_executor import CandleRow
from cryptoforge.entry_risk import EntryRiskPlan
from cryptoforge.exit_rules import price_time_exit
from cryptoforge.spot_buy_math import spot_acquisition,spot_sale

D = Decimal


@dataclass(frozen=True)
class SimulationConfig:
    capital: Decimal = D('100')
    stake: Decimal = D('6')
    max_positions: int = 3
    fee: Decimal = D('0.001')
    slippage: Decimal = D('0.0005')
    spread_fraction: Decimal = D('0')
    stop_fraction: Decimal = D('0.02')
    target_fraction: Decimal = D('0.04')
    hold_bars: int = 12
    entry_delay_bars: int = 1
    min_notional: Decimal = D('5')
    quantity_step: Decimal = D('0.000001')
    max_volume_fraction: Decimal = D('0.01')
    entry_fee: Decimal | None = None
    exit_fee: Decimal | None = None

    def __post_init__(self):
        for name in ('capital','stake','min_notional','quantity_step'):
            value = getattr(self,name)
            if not value.is_finite() or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        for name in ('entry_fee','exit_fee'):
            value=getattr(self,name)
            if value is not None and (not value.is_finite() or not 0<=value<1):
                raise ValueError(f'{name} must be in [0, 1)')
        for name in ('fee','slippage','spread_fraction'):
            value = getattr(self,name)
            if not value.is_finite() or not 0 <= value < 1:
                raise ValueError(f'{name} must be in [0, 1)')
        for name in ('stop_fraction','target_fraction','max_volume_fraction'):
            value = getattr(self,name)
            if not value.is_finite() or not 0 < value < 1:
                raise ValueError(f'{name} must be in (0, 1)')
        if any(type(value) is not int or value<1 for value in (self.max_positions,self.hold_bars,self.entry_delay_bars)):
            raise ValueError('positions, hold and delay must be positive integers')


    @property
    def effective_entry_fee(self):return self.fee if self.entry_fee is None else self.entry_fee

    @property
    def effective_exit_fee(self):return self.fee if self.exit_fee is None else self.exit_fee

    def stress_costs(self,multiplier):
        multiplier=D(multiplier)
        if not multiplier.is_finite() or multiplier<1:raise ValueError('stress multiplier must be at least one')
        return replace(self,entry_fee=self.effective_entry_fee*multiplier,
                       exit_fee=self.effective_exit_fee*multiplier,slippage=self.slippage*multiplier,spread_fraction=self.spread_fraction*multiplier)


@dataclass(frozen=True)
class SimulatedTrade:
    pair: str
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    cost: Decimal
    proceeds: Decimal
    fees: Decimal
    net_pnl: Decimal
    exit_reason: str
    ambiguous: bool


@dataclass(frozen=True)
class SimulationResult:
    trades: tuple[SimulatedTrade, ...]
    rejections: tuple[dict, ...]
    equity: tuple[tuple[datetime, Decimal], ...]
    final_cash: Decimal
    max_drawdown: Decimal
    live_eligible: bool = False
    equity_time_semantics: str = 'candle_close_available_at'
    trade_time_semantics: str = 'bar_open_timestamp_intrabar_order_unknown'
    drawdown_semantics: str = 'conservative_ohlc_low_liquidation_bound_not_exact_execution_path'
    entry_risk_plans: tuple = ()
    spread_assumption: str = 'ohlc_reference_with_scenario_spread_not_historical_bid_ask'
    equity_snapshots: tuple = ()
    entry_fee_currency: str = 'quote'
    exit_fee_currency: str = 'quote'


@dataclass
class _Position:
    pair: str
    signal_time: datetime
    entry_index: int
    quantity: Decimal
    price: Decimal
    cost: Decimal
    entry_fee: Decimal
    stop_fraction: Decimal
    target_fraction: Decimal
    hold_bars: int


def simulate_portfolio(data: Mapping[str, Sequence[CandleRow]],
                       signals: Mapping[str, Sequence[datetime]],
                       config: SimulationConfig = SimulationConfig(), *,
                       entry_risks: Mapping[tuple[str,datetime],EntryRiskPlan] | None = None,
                       capture_equity_details: bool = False) -> SimulationResult:
    """Signals refer to a closed bar's open timestamp; delay=1 fills next open.

    Quote-currency fees, adverse market slippage and no partial fills. Stop wins
    if both barriers touch. History must share a continuous grid. Intrabar lows
    provide a conservative drawdown bound, not an exact executable equity path.
    Volume screening uses the preceding closed bar, never future entry volume.
    """
    if type(capture_equity_details) is not bool:raise ValueError('explicit equity capture flag required')
    if not data or any(not rows for rows in data.values()):
        raise ValueError('nonempty histories required')
    pairs = sorted(data)
    times = [c.open_time for c in data[pairs[0]]]
    if capture_equity_details and len(times)>5000:raise ValueError('detailed equity capture limited to 5000 bars')
    if len(times) < 2 or any(t.tzinfo is None for t in times):
        raise ValueError('at least two timezone-aware candles required')
    spacing = times[1]-times[0]
    if spacing.total_seconds() <= 0 or any(b-a != spacing for a,b in zip(times,times[1:])):
        raise ValueError('history must be continuous and unique')
    for pair,rows in data.items():
        if [c.open_time for c in rows] != times:
            raise ValueError('pair histories must share a continuous grid')
        for c in rows:
            if c.pair != pair or c.symbol!=pair.replace('/','') or not all(v.is_finite() for v in (c.open,c.high,c.low,c.close,c.volume)) or not (
                0 < c.low <= min(c.open,c.close) <= max(c.open,c.close) <= c.high and c.volume >= 0
            ):
                raise ValueError('invalid candle')
    lookup = {t:i for i,t in enumerate(times)}
    pending: dict[int,list[tuple[str,datetime]]] = {}
    rejections=[]
    for pair,stamps in signals.items():
        if pair not in data:
            raise ValueError('signal pair missing from history')
        for stamp in sorted(set(stamps)):
            if stamp not in lookup:
                raise ValueError('signal timestamp missing from history')
            index=lookup[stamp]+config.entry_delay_bars
            if index >= len(times):
                rejections.append({'pair':pair,'time':stamp,'reason':'no_future_bar'})
            else:
                pending.setdefault(index,[]).append((pair,stamp))
    if entry_risks is not None:
        expected={(pair,stamp) for pair,stamps in signals.items() for stamp in stamps}
        if set(entry_risks)!=expected:raise ValueError('exact risk plan coverage of signals required')
        for (pair,stamp),plan in entry_risks.items():
            if not isinstance(plan,EntryRiskPlan) or (plan.pair,plan.signal_time)!=(pair,stamp):
                raise ValueError('risk plan signal identity mismatch')
            fill_index=lookup[stamp]+config.entry_delay_bars
            earliest=stamp+spacing
            if plan.information_available_at<earliest or (fill_index<len(times) and plan.information_available_at>times[fill_index]):
                raise ValueError('risk plan unavailable at entry time')
    cash=config.capital
    positions: dict[str,_Position]={}
    trades=[]
    equity=[];equity_snapshots=[]
    peak=config.capital
    drawdown=D(0);realized_total=D(0)

    bid_factor=1-config.spread_fraction/2
    ask_factor=1+config.spread_fraction/2

    def close(pair,index,bid_price,reason,ambiguous=False):
        nonlocal cash,realized_total
        pos=positions.pop(pair)
        price=bid_price*(1-config.slippage)
        sale=spot_sale(quantity=pos.quantity,price=price,fee_fraction=config.effective_exit_fee,fee_currency='quote')
        exit_fee=sale.fee_amount;proceeds=sale.cash_proceeds
        cash+=proceeds
        realized_total+=proceeds-pos.cost
        trades.append(SimulatedTrade(pair,pos.signal_time,times[pos.entry_index],times[index],
                                    pos.quantity,pos.price,price,pos.cost,proceeds,
                                    pos.entry_fee+exit_fee,proceeds-pos.cost,reason,ambiguous))

    for index,time in enumerate(times):
        # Only opening-time exits can finance another opening-time entry.
        for pair in sorted(list(positions)):
            pos=positions[pair]; candle=data[pair][index]
            reason=price_time_exit(price=candle.open*bid_factor,entry_price=pos.price,stop_fraction=pos.stop_fraction,
                target_fraction=pos.target_fraction,elapsed_seconds=(index-pos.entry_index)*spacing.total_seconds(),
                maximum_hold_seconds=pos.hold_bars*spacing.total_seconds())
            if reason is not None:
                close(pair,index,candle.open*bid_factor,{'stop':'stop_gap','target':'target_gap','timeout':'timeout'}[reason])
        for pair,stamp in sorted(pending.get(index,[])):
            reason=None
            if pair in positions:
                reason='already_open'
            elif len(positions) >= config.max_positions:
                reason='position_limit'
            else:
                price=data[pair][index].open*ask_factor*(1+config.slippage)
                purchase=spot_acquisition(stake=config.stake,price=price,quantity_step=config.quantity_step,
                    fee_fraction=config.effective_entry_fee,fee_currency='quote')
                quantity=purchase.net_quantity;notional=purchase.notional;cost=purchase.cash_cost
                if quantity <= 0 or notional < config.min_notional:
                    reason='minimum_order'
                elif cost > cash:
                    reason='insufficient_cash'
                elif quantity > data[pair][index-1].volume*config.max_volume_fraction:
                    reason='liquidity_limit'
                else:
                    cash-=cost
                    risk=entry_risks[(pair,stamp)] if entry_risks is not None else None
                    positions[pair]=_Position(pair,stamp,index,quantity,price,cost,notional*config.effective_entry_fee,
                        risk.stop_fraction if risk else config.stop_fraction,risk.target_fraction if risk else config.target_fraction,
                        risk.hold_bars if risk else config.hold_bars)
            if reason:
                rejections.append({'pair':pair,'time':time,'reason':reason})
        # Newly filled positions can already breach their stop at this open.
        # Settle after all pending opening entries; do not lend their proceeds
        # to another simultaneous entry or include post-exit candle extremes.
        for pair in sorted(list(positions)):
            pos=positions[pair];candle=data[pair][index]
            if candle.open*bid_factor<=pos.price*(1-pos.stop_fraction):
                close(pair,index,candle.open*bid_factor,'stop_gap')
        # Record conservative simultaneous lows before intrabar exits.
        low_equity=cash+sum((p.quantity*data[pair][index].low*bid_factor*(1-config.slippage)*(1-config.effective_exit_fee)
                            for pair,p in positions.items()),D(0))
        drawdown=max(drawdown,1-low_equity/peak)
        for pair in sorted(list(positions)):
            pos=positions[pair]; candle=data[pair][index]
            stop=pos.price*(1-pos.stop_fraction); target=pos.price*(1+pos.target_fraction)
            if candle.open*bid_factor<=stop:
                # An adverse entry fill can put the stop above the current
                # market. Exit at that available open, not a better stop price.
                close(pair,index,candle.open*bid_factor,'stop_gap')
            elif candle.low*bid_factor <= stop:
                close(pair,index,stop,'stop',candle.high*bid_factor >= target)
            elif candle.high*bid_factor >= target:
                close(pair,index,target,'target')
        if index == len(times)-1:
            for pair in sorted(list(positions)):
                close(pair,index,data[pair][index].close*bid_factor,'end_of_data')
        mark=cash+sum((p.quantity*data[pair][index].close*bid_factor*(1-config.slippage)*(1-config.effective_exit_fee)
                       for pair,p in positions.items()),D(0))
        peak=max(peak,mark)
        drawdown=max(drawdown,1-mark/peak)
        equity.append((time+spacing,mark))
        if capture_equity_details:
            inventory=[]
            for pair,pos in sorted(positions.items()):
                liquidation=pos.quantity*data[pair][index].close*bid_factor*(1-config.slippage)*(1-config.effective_exit_fee)
                inventory.append({'pair':pair,'quantity':pos.quantity,'cost_basis':pos.cost,
                    'entry_time':times[pos.entry_index],'liquidation_estimate':liquidation,
                    'unrealized_net_pnl_estimate':liquidation-pos.cost})
            basis=sum((row['cost_basis'] for row in inventory),D(0))
            realized=realized_total
            if abs(cash+basis-config.capital-realized)>D('1e-20'):raise ValueError('equity cash/basis reconciliation failed')
            equity_snapshots.append({'available_at':time+spacing,'cash':cash,'open_cost_basis':basis,
                'realized_net_pnl':realized,'equity':mark,'open_positions':inventory,
                'valuation_scope':'close_bid_proxy_adverse_slippage_quote_fees_not_actual_executable_equity'})
    return SimulationResult(tuple(trades),tuple(rejections),tuple(equity),cash,drawdown,
        entry_risk_plans=tuple(entry_risks[key] for key in sorted(entry_risks)) if entry_risks is not None else (),equity_snapshots=tuple(equity_snapshots))
