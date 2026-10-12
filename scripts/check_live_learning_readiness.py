"""Report prospective sample readiness, never fit or publish a model."""
from cryptoforge.atomic_reports import write_json_report
from datetime import UTC,datetime,timedelta
import argparse
import hashlib
import json
from pathlib import Path

from cryptoforge.entry_gate_diagnostics import current_gate_diagnostic
from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import load_protocol,split_cutoff,evaluate_readiness,SPLITS,time,collection_is_healthy,collection_contract_counts
from cryptoforge.collection_contract_diagnostics import describe_collection_contract
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def latest_saved_primary_input(directory,now):
    latest=None
    for path in directory.glob('pure-python-logistic-*.json'):
        try:
            raw=path.read_bytes();artifact=json.loads(raw);stamp=time(artifact['trained_at'])
            if (stamp>now or not path.stem.endswith('-'+hashlib.sha256(raw).hexdigest()[:12])
                or artifact.get('model_family')!='pure-python-logistic'
                or artifact.get('feature_version')!='candle-v1'):continue
            if latest is None or stamp>latest[0]:latest=(stamp,artifact)
        except (ValueError,KeyError,TypeError,OSError):continue
    if latest is None:return None
    artifact=latest[1];config=artifact.get('config') or {}
    return {'feature_version':artifact['feature_version'],'timeframe':config.get('timeframe','5m'),
        'input_candle_state':config.get('input_candle_state','legacy_asof_snapshot'),
        'calculation_contract':config.get('feature_calculation_contract'),
        'lookback_candles':config.get('feature_lookback_candles')}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();now=datetime.now(UTC);path=args.protocol;protocol,study=load_cash_study(path)
    dataset_path=Path('.local/state/cash-recovery-dataset.json')
    current=json.loads(dataset_path.read_bytes()) if dataset_path.exists() else {}
    source_healthy=collection_is_healthy(current,protocol,now)
    memory=Path('.local/state/live-experience-memory.sqlite')
    snapshots={split:available_experiences(memory,target=protocol['target_version'],as_of=split_cutoff(protocol,split,now))
               for split in SPLITS}
    result=evaluate_readiness(protocol,snapshots,as_of=now,source_healthy=source_healthy)
    try:result['collection_protocol_freeze']=require_collection_freeze(study)
    except ValueError:
        result['collection_protocol_freeze']='missing_observed_freeze'
        result['data_ready_for_offline_fit']=False
        result['blocked_reasons'].append('collection_protocol_has_no_observed_freeze')
    current_rows=available_experiences(memory,target=protocol['target_version'],as_of=now)
    result['collection_input_contracts']=collection_contract_counts(current_rows)
    result['protocol_expected_input_contract']=protocol['input_candle_state']
    result['collection_contract_diagnostics']=describe_collection_contract(protocol,current_rows,
        primary_input=latest_saved_primary_input(Path('.local/models'),now))
    gate_path=Path('.local/state/current-entry-gate-diagnostics.json')
    try:gate_report=json.loads(gate_path.read_bytes())
    except (OSError,ValueError):gate_report={}
    result['recent_entry_gate_diagnostics']=current_gate_diagnostic(gate_report,now=now)
    result['protocol_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    output=study.readiness
    output.parent.mkdir(parents=True,exist_ok=True);write_json_report(output,result)
    print(json.dumps({'data_ready_for_offline_fit':result['data_ready_for_offline_fit'],
        'counts':{s:result['splits'][s]['counts'] for s in SPLITS},'blocked':result['blocked_reasons'],
        'input_compatibility':result['collection_contract_diagnostics']['status'],
        'collection_flow':result['recent_entry_gate_diagnostics']['status'],
        'train_failures':result['splits']['train']['failures'],
        'promotion_allowed':False,'output':str(output.resolve())}))


if __name__=='__main__':main()
