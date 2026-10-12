"""Three fixed experimental net heads, train/validation only, no publication."""
from dataclasses import asdict
from datetime import UTC,datetime
from decimal import Decimal
import argparse,hashlib,inspect,json
from pathlib import Path

from cryptoforge.archive import ArchiveReader
from cryptoforge.trade_labels import build_trade_labels,TARGET_VERSION
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.net_regression import fit_net_regressor,evaluate_net_regressor
from cryptoforge.model_training import fit_standardizer
from cryptoforge.supabase_executor import rsi
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.source_contract import source_hashes,net_research_sources
from cryptoforge.atomic_reports import write_json_report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=Path('config/net-regression-research-v2.json'))
    args=parser.parse_args();protocol_path=args.protocol;raw=protocol_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=protocol_path.with_suffix('.sha256').read_text().strip():raise ValueError('frozen net protocol checksum mismatch')
    from cryptoforge.research_protocol import prepare_research
    protocol=prepare_research(str(protocol_path));policy=protocol['net_head_policy']
    if policy['target_version']!=TARGET_VERSION or policy['live_eligible'] is not False:raise ValueError('experimental net protocol required')
    dependencies=net_research_sources('net_head',fit_net_regressor,runner=main)
    dependencies['report_writer']=write_json_report
    original_sources=source_hashes(dependencies)
    reader=ArchiveReader(Path('.local/archive'),protocol=protocol);cfg=SimulationConfig()
    train=[];validation=[];ranges={};digests={}
    for pair in protocol['baseline_pairs']:
        rows=reader.read_candles(pair,limit=policy['max_candles_per_pair']);n=len(rows)
        if n<1000:raise ValueError('insufficient development history')
        boundary=rows[int(n*float(policy['train_fraction']))].open_time
        end=rows[int(n*float(policy['validation_end_fraction']))].open_time
        development=[row for row in rows if row.open_time<end]
        examples=[label.example for label in build_trade_labels(pair,development,cfg) if label.example is not None]
        train.extend(row for row in examples if row.open_time<boundary and row.label_end_time<boundary)
        validation.extend(row for row in examples if row.open_time>=boundary and row.label_end_time<end)
        ranges[pair]={'validation_start':boundary.isoformat(),'development_end':end.isoformat()}
        digests[pair]=hashlib.sha256(json.dumps([asdict(row) for row in development],default=str,sort_keys=True).encode()).hexdigest()
    if min(len(train),len(validation))<100:raise ValueError('insufficient purged net examples')
    train.sort(key=lambda row:(row.open_time,row.pair));validation.sort(key=lambda row:(row.open_time,row.pair))
    train_cutoff=min(datetime.fromisoformat(r['validation_start']) for r in ranges.values())
    validation_cutoff=min(datetime.fromisoformat(r['development_end']) for r in ranges.values())
    grid=[{'family':'ridge-net-return','ridge':value} for value in policy['ridge_values']]
    manifest={'grid':grid,'base_config':asdict(cfg),'ranges':ranges,'dataset_sha256':digests,'target_version':TARGET_VERSION,
        'scope':policy['scope'],'outer_test_evaluated':False,'historical_reserved_final_compatible':False,
        'implementation_hashes':original_sources}
    if source_hashes(dependencies)!=original_sources:raise ValueError('research source changed during label preparation')
    ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'));protocol_sha=hashlib.sha256(raw).hexdigest()
    study=ledger.register(manifest,protocol_id=protocol_sha,protocol_version=protocol['protocol_version'],maximum_per_family=3)
    results=[]
    for candidate in grid:
        prior=ledger.result(study,candidate)
        if prior is not None:results.append(prior);continue
        try:
            model=fit_net_regressor(train,target_version=TARGET_VERSION,ridge=float(candidate['ridge']),as_of=train_cutoff)
            metrics=evaluate_net_regressor(model,validation,target_version=TARGET_VERSION,as_of=validation_cutoff)
            if source_hashes(dependencies)!=original_sources:raise ValueError('research source changed during fitting')
            result={'parameters':candidate,'metrics':metrics,'model':asdict(model)}
        except Exception as exc:
            ledger.record(study,candidate,{'error':type(exc).__name__},failed=True);raise
        ledger.record(study,candidate,result);results.append(result)
    mean=sum(row.future_return for row in train)/len(train)
    import math
    baseline={'mae':sum(abs(mean-row.future_return) for row in validation)/len(validation),
              'rmse':math.sqrt(sum((mean-row.future_return)**2 for row in validation)/len(validation))}
    winner=min(results,key=lambda result:result['metrics']['rmse'])
    report={**manifest,'protocol_version':protocol['protocol_version'],'protocol_sha256':protocol_sha,'as_of':datetime.now(UTC).isoformat(),'study_sha256':study,'results':results,
        'constant_train_mean_baseline':baseline,'selected_ridge':winner['parameters']['ridge'],
        'train_count':len(train),'validation_count':len(validation),'live_promotion_allowed':False,
        'status':'development_net_prediction_diagnostics_only'}
    if source_hashes(dependencies)!=original_sources:raise ValueError('research source changed before report export')
    path=Path('.local/state/archive-net-head-report.json');write_json_report(path,report,default=str)
    print(json.dumps({'status':report['status'],'train':len(train),'validation':len(validation),
        'selected_ridge':report['selected_ridge'],'metrics':winner['metrics'],'baseline':baseline,'live_promotion_allowed':False}))


if __name__=='__main__':main()
