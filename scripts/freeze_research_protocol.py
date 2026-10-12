"""Capture sanitized runtime and freeze a development protocol; no live mutations."""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import resource
import shlex
import shutil
import subprocess
import time

from cryptoforge.archive import ArchiveReader
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.supabase_market import SupabaseRestClient
from cryptoforge.research_protocol import validate_protocol, assert_resources, assert_executor_compatible
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig


def main():
    path=Path('config/research-protocol-v1.json')
    protocol=json.loads(path.read_text())
    if protocol.get('status')=='frozen_development_only':
        raise SystemExit('Protocol already frozen; create a new version for changes.')
    now=datetime.now(UTC)
    allowed={'--ml-mode','--ml-threshold','--ml-max-age-hours','--stake-amount','--max-open-positions',
             '--max-daily-loss','--stop-loss-percent','--timeout'}
    raw=subprocess.check_output(['systemctl','--user','show','cryptoforge-supabase-executor.service',
                                 '--property=ExecStart','--value'],text=True)
    tokens=shlex.split(raw)
    runtime={key:tokens[i+1] for i,key in enumerate(tokens[:-1]) if key in allowed}
    runtime['live']='--live' in tokens
    client=SupabaseRestClient.from_env(timeout_seconds=20)
    model=ActiveModelRegistry(client).latest(max_age=timedelta(days=36500))
    snapshot={'captured_at':now.isoformat(),'executor_flags':runtime,
              'active_model':None if model is None else {
                  'version':model.model_version,'run_id':model.model_run_id,
                  'checksum':model.artifact_sha256,'feature_version':model.feature_version,
                  'published_at':model.occurred_at.isoformat(),'config':model.artifact.get('config',{}),
                  'threshold':model.artifact.get('threshold')}}
    cfg=SimulationConfig()
    reader=ArchiveReader(Path('.local/archive'))
    datasets=[]
    for pair in protocol['baseline_pairs']:
        file=Path('.local/archive')/(pair.replace('/','')+'-5.json')
        rows=reader.read_candles(pair,limit=1000000)
        datasets.append({'pair':pair,'path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                         'candles':len(rows),'start':rows[0].open_time.isoformat(),'end':rows[-1].open_time.isoformat()})
    began=time.monotonic()
    labels=build_trade_labels('BTC/USDT',reader.read_candles('BTC/USDT',limit=1000),cfg)
    measurement={'pilot_candles':1000,'labels':len(labels),'wall_seconds':round(time.monotonic()-began,3),
                 'process_peak_rss_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)}
    meminfo={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    measurement.update(available_memory_mb=round(meminfo['MemAvailable']/1024,2),
                       free_disk_mb=round(shutil.disk_usage('.').free/1024**2,2))
    protocol.update(protocol_version='research-v1',status='frozen_development_only',frozen_at=now.isoformat(),
                    datasets=datasets,portfolio={k:str(v) if not isinstance(v,int) else v for k,v in asdict(cfg).items()},
                    data_policy={'development_end':now.isoformat(),'previously_viewed_policy':'all history through freeze is development; no retrospective final test',
                                 'final_reserved_start':'2026-10-08T00:00:00+00:00','final_reserved_end':'2026-11-08T00:00:00+00:00',
                                 'final_reserved_status':'future_not_available_do_not_evaluate_during_search'},
                    resources={'max_parallel_experiments':1,'worker_nice':10,'max_wall_seconds':120,
                               'max_worker_memory_mb':768,'min_available_memory_mb':1536,'min_free_disk_mb':2048,
                               'max_output_file_mb':128},measurements=measurement,
                    runtime_snapshot_path='.local/state/research-v1-runtime.json',
                    required_before_execution=['verify_dataset_sha256','enforce_development_range','enforce_resource_caps'],
                    cost_assumptions={**protocol['cost_assumptions'],'verified':False,
                                      'policy':'conservative scenario assumption; cannot establish live profitability'})
    if float(protocol['portfolio']['stake'])>float(runtime.get('--stake-amount','0')):
        raise ValueError('development stake exceeds recorded runtime stake')
    validate_protocol(protocol)
    try:
        assert_resources(protocol,measurement['available_memory_mb'],measurement['free_disk_mb'])
        protocol['resource_readiness']={'ready':True}
    except ValueError as exc:
        protocol['resource_readiness']={'ready':False,'reason':str(exc)}
    if model:
        try:
            assert_executor_compatible(model.artifact,feature_version='candle-v1',timeframe='5m',
                                       horizon=3,threshold=float(runtime.get('--ml-threshold',0.5)),target_version='fixed-future-return-v1')
            snapshot['model_contract']='matching_legacy_contract'
        except ValueError:
            snapshot['model_contract']='mismatch_requires_review_no_deployment'
    dest=Path(protocol['runtime_snapshot_path']);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(snapshot,indent=2));dest.chmod(0o600)
    path.write_text(json.dumps(protocol,indent=2)+'\n')
    print(json.dumps({'protocol':str(path),'measurement':measurement,'model_contract':snapshot.get('model_contract'),
                      'executor_flags':runtime,'status':protocol['status']}))


if __name__=='__main__':
    main()
