"""Bounded source-bound development window comparison; no publication/orders."""
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.net_regression import fit_net_regressor
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes,net_research_sources
from cryptoforge.trade_labels import build_trade_labels,TARGET_VERSION
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.train_window_study import run_train_window_study
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.research_environment import research_environment


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    raw=args.protocol.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=args.protocol.with_suffix('.sha256').read_text().strip():
        raise ValueError('frozen window protocol checksum mismatch')
    protocol=prepare_research(str(args.protocol));policy=protocol['window_study_policy']
    if policy['target_version']!=TARGET_VERSION or policy['live_eligible'] is not False:
        raise ValueError('research net target required')
    if type(policy['max_candles_per_pair']) is not int or not 1000<=policy['max_candles_per_pair']<=2000:
        raise ValueError('bounded 1000..2000 candle development slice required')
    cfg=SimulationConfig()
    if json.loads(json.dumps(asdict(cfg),default=str))!=protocol['portfolio']:
        raise ValueError('frozen execution assumptions differ from simulator')
    dependencies=net_research_sources('net_head',fit_net_regressor,runner=Path(__file__))
    dependencies.update(window_study=run_train_window_study,report_writer=write_json_report,
                        research_guard=prepare_research,runtime_capture=save_runtime_sources,
                        environment_receipt=research_environment)
    hashes=source_hashes(dependencies)
    if hashes!=policy['implementation_hashes']:
        raise ValueError('window runner differs from observed protocol source freeze')
    runtime=save_runtime_sources(Path('.local/state/net-window-archive-runtime'),dependencies,hashes)
    histories={}
    for pair in protocol['baseline_pairs']:
        dataset=next(row for row in protocol['datasets'] if row['pair']==pair)
        histories[pair]=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(
            pair,limit=policy['max_candles_per_pair'])
    grids=[tuple(row.open_time for row in rows) for rows in histories.values()]
    if not grids or any(grid!=grids[0] for grid in grids) or len(grids[0])<1000:
        raise ValueError('aligned complete development histories required')
    times=grids[0];n=len(times)
    start=times[int(n*.70)];end=times[int(n*.85)]
    train=[];validation=[];digests={}
    for pair,rows in histories.items():
        development=[row for row in rows if row.open_time<end]
        digests[pair]=hashlib.sha256(json.dumps([asdict(row) for row in development],sort_keys=True,default=str).encode()).hexdigest()
        examples=[label.example for label in build_trade_labels(pair,development,cfg) if label.example is not None]
        train.extend(row for row in examples if row.open_time<start and row.label_end_time<=start)
        validation.extend(row for row in examples if start<row.open_time and row.label_end_time<=end)
    if min(len(train),len(validation))<100:
        raise ValueError('at least100 purged examples per split required')
    train.sort(key=lambda row:(row.open_time,row.pair));validation.sort(key=lambda row:(row.open_time,row.pair))
    if hashes!=source_hashes(dependencies):raise ValueError('archive window source changed before fit')
    report=run_train_window_study(train,validation,grid=policy['grid'],train_end=start,
        validation_end=end,target_version=TARGET_VERSION,ridge=float(policy['ridge']),
        ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite')),
        protocol_id=sha,protocol_version=protocol['protocol_version'],
        maximum_per_family=protocol['search_limits']['max_configurations_per_family'],
        study_context={'protocol_sha256':sha,'execution_config':asdict(cfg),
            'development_dataset_sha256':digests,'archive_source_hashes':hashes,
            'environment':research_environment(Path.cwd()),
            'original_archive_runtime_sources':runtime,'slice_policy':'tail2000_70train_85development_v1'})
    if hashes!=source_hashes(dependencies):raise ValueError('archive window source changed before export')
    write_json_report(args.output,report,default=str)
    print(json.dumps({'study_sha256':report['study_sha256'],'results':[
        {key:result[key] for key in ('parameters','metrics','train_count','effective_sample_size')}
        for result in report['results']],'live_promotion_allowed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
