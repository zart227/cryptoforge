"""Replay saved label windows read-only; no archive scan, fit, or human sign-off."""
import argparse,json,hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from cryptoforge.execution_market_evidence import _load
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.source_contract import net_research_sources,assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources
from scripts.audit_trade_labels import verify_trade


def validate_case_coverage(report):
    groups=report['pairs'];pairs=set();cases=set()
    if not groups:raise ValueError('nonempty source case groups required')
    for group in groups:
        pair=group['pair']
        if pair in pairs:raise ValueError('unique source market groups required')
        pairs.add(pair)
        samples=group['samples'];refs=group['sample_source_references']
        count=group['audited_samples']
        if type(count) is not int or count<=0 or len(samples)!=count or len(refs)!=count:
            raise ValueError('complete positive source case coverage required')
        for sample,reference in zip(samples,refs):
            time=datetime.fromisoformat(sample['signal_time'])
            reference_time=datetime.fromisoformat(reference['signal_time'])
            if time.tzinfo is None or reference_time.tzinfo is None:
                raise ValueError('aware source case timestamps required')
            identity=(pair,time)
            if sample['pair']!=pair or reference['pair']!=pair or time!=reference_time:
                raise ValueError('source case group identity mismatch')
            if identity in cases:raise ValueError('globally unique paired source cases required')
            cases.add(identity)
    return len(cases)


def replay_report(path):
    if not __debug__:raise ValueError('audit assertions must remain enabled')
    if path.stat().st_size>5*1024**2:raise ValueError('bounded audit receipt required')
    report=json.loads(path.read_bytes())
    expected_count=validate_case_coverage(report)
    deps=net_research_sources('label_builder',build_trade_labels,runner=Path(__file__).with_name('audit_trade_labels.py').resolve())
    assert_source_dependencies(report['implementation_hashes'],deps)
    load_runtime_sources(report['runtime_source_bundle'],report['implementation_hashes'])
    numeric={'capital','stake','fee','slippage','spread_fraction','stop_fraction','target_fraction','min_notional','quantity_step','max_volume_fraction','entry_fee','exit_fee'}
    cfg=SimulationConfig(**{key:Decimal(value) if key in numeric and value is not None else value for key,value in report['config'].items()})
    count=0;categories={}
    for group in report['pairs']:
        samples=group['samples'];refs=group['sample_source_references']
        if len(samples)!=len(refs) or len(samples)!=group['audited_samples']:raise ValueError('complete source references required')
        seen=set()
        for sample,reference in zip(samples,refs):
            identity=(sample['pair'],datetime.fromisoformat(sample['signal_time']))
            if identity in seen or identity!=(reference['pair'],datetime.fromisoformat(reference['signal_time'])):raise ValueError('unique paired source cases required')
            seen.add(identity)
            if reference['input_sha256']!=reference['input_reference']['sha256']:raise ValueError('case input checksum identity mismatch')
            rows=[]
            for raw in _load(reference['input_reference']):
                values={**raw,'open_time':datetime.fromisoformat(raw['open_time']),
                    **{key:Decimal(raw[key]) for key in ('open','high','low','close','volume')}}
                if values.get('cache_observed_at') is not None:values['cache_observed_at']=datetime.fromisoformat(values['cache_observed_at'])
                rows.append(CandleRow(**values))
            trade={key:datetime.fromisoformat(value) if key.endswith('_time') else Decimal(value)
                   if key in {'quantity','entry_price','exit_price','cost','proceeds','fees','net_pnl'} else value
                   for key,value in sample['trade'].items()}
            if trade['pair']!=sample['pair'] or any(row.pair!=sample['pair'] or row.symbol!=sample['pair'].replace('/','') for row in rows):
                raise ValueError('case market identity differs from original window')
            risk={key:datetime.fromisoformat(value) if key=='outcome_available_at' else Decimal(value)
                  if key.startswith('maximum_') else value for key,value in sample['risk_outcome'].items()}
            label=SimpleNamespace(signal_time=datetime.fromisoformat(sample['signal_time']),trade=SimpleNamespace(**trade),
                example=SimpleNamespace(**sample['example']),label_end_time=datetime.fromisoformat(sample['label_end_time']),risk_outcome=risk)
            verify_trade(label,rows,cfg);count+=1
            category=trade['exit_reason']+(':ambiguous' if trade['ambiguous'] else ':unambiguous')
            categories[category]=categories.get(category,0)+1
    if count!=expected_count:raise ValueError('replay coverage changed')
    return {'source_report_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'replayed_cases':count,
        'categories':categories,'original_windows_and_runtime_verified':True,'feature_preprocessing_replayed':False,
        'manual_review_completed':False,'historical_execution_certified':False,'live_promotion_allowed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(replay_report(args.report)))


if __name__=='__main__':main()
