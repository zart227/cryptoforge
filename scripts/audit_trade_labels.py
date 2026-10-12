"""Audit development train labels with independent arithmetic; do not read test outcomes."""
import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.archive import ArchiveReader
from cryptoforge.trade_labels import build_trade_labels,TARGET_VERSION
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.trade_risk_labels import RISK_TARGET_VERSION


def verify_trade(label,rows,cfg):
    lookup={c.open_time:i for i,c in enumerate(rows)}
    trade=label.trade
    signal_index=lookup[label.signal_time]
    entry_index=signal_index+cfg.entry_delay_bars
    bid_factor=1-cfg.spread_fraction/2
    price=rows[entry_index].open*(1+cfg.spread_fraction/2)*(1+cfg.slippage)
    quantity=(cfg.stake/(price*(1+cfg.effective_entry_fee))/cfg.quantity_step).to_integral_value(rounding=ROUND_DOWN)*cfg.quantity_step
    stop=price*(1-cfg.stop_fraction);target=price*(1+cfg.target_fraction)
    raw=None; reason=None
    for index in range(entry_index,entry_index+cfg.hold_bars+1):
        candle=rows[index]
        # The position has filled before its stop is evaluated, including an
        # entry whose adverse fill is already above the raw market stop.
        if candle.open*bid_factor<=stop:
            raw,reason=candle.open*bid_factor,'stop_gap'
        elif index>entry_index and candle.open*bid_factor>=target:
            raw,reason=candle.open*bid_factor,'target_gap'
        elif index-entry_index>=cfg.hold_bars:
            raw,reason=candle.open*bid_factor,'timeout'
        elif candle.low*bid_factor<=stop:
            raw,reason=stop,'stop'
        elif candle.high*bid_factor>=target:
            raw,reason=target,'target'
        if raw is not None:
            break
    assert raw is not None
    sell_price=raw*(1-cfg.slippage)
    cost=quantity*price*(1+cfg.effective_entry_fee)
    proceeds=quantity*sell_price*(1-cfg.effective_exit_fee)
    assert (trade.quantity,trade.entry_price,trade.exit_price,trade.exit_reason,trade.exit_time)==(quantity,price,sell_price,reason,rows[index].open_time)
    assert abs(trade.net_pnl-(proceeds-cost))<Decimal('1e-20')
    assert label.example.label==int(proceeds>cost)
    assert abs(Decimal(str(label.example.future_return))-(proceeds-cost)/cost)<Decimal("1e-12")
    assert label.label_end_time>trade.exit_time
    risk=label.risk_outcome
    assert risk['risk_target_version']==RISK_TARGET_VERSION
    assert risk['outcome_available_at']==label.label_end_time
    for kind in ('adverse','favorable'):
        assert 0<=risk[f'maximum_{kind}_price_fraction_lower_bound']<=risk[f'maximum_{kind}_price_fraction_upper_bound']
    assert risk['holding_seconds_lower_bound']<=risk['holding_seconds_upper_bound']
    assert not risk['price_bounds_include_fees']
    # Independently reconstruct the pre-exit path from the audited exit index.
    intrabar=reason in {'stop','target'}
    path=rows[entry_index:index]
    guaranteed=[price,raw,rows[index].open*bid_factor]
    minimum=min([*guaranteed,*[row.low*bid_factor for row in path]])
    maximum=max([*guaranteed,*[row.high*bid_factor for row in path]])
    possible_minimum=min(minimum,rows[index].low*bid_factor) if intrabar else minimum
    possible_maximum=max(maximum,rows[index].high*bid_factor) if intrabar else maximum
    expected={
        'maximum_adverse_price_fraction_lower_bound':max(Decimal(0),1-minimum/price),
        'maximum_adverse_price_fraction_upper_bound':max(Decimal(0),1-possible_minimum/price),
        'maximum_favorable_price_fraction_lower_bound':max(Decimal(0),maximum/price-1),
        'maximum_favorable_price_fraction_upper_bound':max(Decimal(0),possible_maximum/price-1)}
    for key,value in expected.items():assert risk[key]==value
    duration=(rows[index].open_time-rows[entry_index].open_time).total_seconds()
    assert risk['holding_seconds_lower_bound']==duration
    assert risk['holding_seconds_upper_bound']==duration+((rows[1].open_time-rows[0].open_time).total_seconds() if intrabar else 0)
    assert risk['exit_bar_order_unknown'] is intrabar


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--max-candles',type=int,default=5000)
    parser.add_argument('--directory',type=Path,default=Path('.local/archive'))
    parser.add_argument('--output',type=Path,default=Path('.local/state/trade-label-audit.json'))
    args=parser.parse_args()
    from cryptoforge.research_protocol import prepare_research
    protocol = prepare_research()
    reader=ArchiveReader(args.directory, protocol=protocol);cfg=SimulationConfig();report=[]
    for pair in dict.fromkeys(args.pair):
        all_rows=reader.read_candles(pair,limit=args.max_candles)
        rows=all_rows[:int(len(all_rows)*0.7)]
        labels=build_trade_labels(pair,rows,cfg)
        executed=[l for l in labels if l.trade]
        counts=Counter(l.trade.exit_reason for l in executed)
        buckets={}
        for label in executed:
            key=(label.trade.exit_reason,label.example.label,label.trade.ambiguous)
            buckets.setdefault(key,[]).append(label)
        samples=[]
        for bucket in buckets.values():
            samples.extend(bucket[i] for i in sorted(set([0,len(bucket)//2,len(bucket)-1])))
        for label in executed:
            if len(samples)>=20:
                break
            if label not in samples:
                samples.append(label)
        for sample in samples:
            verify_trade(sample,rows,cfg)
        digest=hashlib.sha256(json.dumps([asdict(c) for c in rows],default=str,sort_keys=True).encode()).hexdigest()
        monthly={}
        for label in executed:
            key=label.signal_time.strftime('%Y-%m')
            bucket=monthly.setdefault(key,{'count':0,'positive':0})
            bucket['count']+=1;bucket['positive']+=label.example.label
        report.append({'pair':pair,'scope':'first_70_percent_development_train_only',
                       'candles':len(rows),'start':str(rows[0].open_time),'end':str(rows[-1].open_time),
                       'dataset_sha256':digest,'executed':len(executed),'rejected':len(labels)-len(executed),
                       'positive_rate':sum(l.example.label for l in executed)/max(len(executed),1),
                       'exit_reasons':dict(counts),'monthly':monthly,'audited_samples':len(samples),
                       'risk_bounds_samples_checked':len(samples),
                       'samples':[asdict(l) for l in samples],
                       'audit':'independent_arithmetic_passed_not_human_review'})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(args.output,{'target_version':TARGET_VERSION,'risk_target_version':RISK_TARGET_VERSION,'counts_as_real_executed_buys':False,'independent_trade_labels_may_overlap':True,'portfolio_profitability_established':False,'numeric_target':'net_pnl_divided_by_total_entry_cost','config':asdict(cfg),'pairs':report},default=str)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('samples','monthly')} for r in report]))


if __name__=='__main__':
    main()
