"""Observed fixed passive context, separate from strategy ranking and admission."""
import argparse,json,hashlib
from dataclasses import asdict
from pathlib import Path
from datetime import datetime,UTC
from cryptoforge.buy_hold_context import buy_hold_context
from cryptoforge.archive import ArchiveReader
from cryptoforge.trade_simulator import SimulationConfig
from cryptoforge.research_attempts import ResearchAttempts,identity
from cryptoforge.research_protocol import prepare_research,validate_protocol
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources,_save_raw
from cryptoforge.atomic_reports import write_json_report

ROOT=Path(__file__).resolve().parents[1]


def dependencies():
    return net_research_sources('passive',buy_hold_context,runner=Path(__file__).resolve())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--register',action='store_true');group.add_argument('--receipt',type=Path)
    args=parser.parse_args();directory=ROOT/'.local/state/passive-context-studies'
    ledger=ResearchAttempts(ROOT/'.local/state/research-attempts.sqlite')
    cfg=SimulationConfig(exit_minimum_policy='preserve_inventory')
    if args.register:
        raw=(ROOT/'config/research-protocol-v1.json').read_bytes();protocol=json.loads(raw);validate_protocol(protocol)
        for dataset in protocol['datasets']:
            if hashlib.sha256((ROOT/dataset['path']).read_bytes()).hexdigest()!=dataset['sha256']:raise ValueError('original data changed')
        hashes=source_hashes(dependencies());runtime=save_runtime_sources(directory/'runtime',dependencies(),hashes)
        manifest={'scope':'fixed_stake_buy_hold_development_context','grid':[{'family':'buy_hold_context','entry_index':120}],
            'base_config':asdict(cfg),'input_policy':'tail5000_first3500_development','pairs':protocol['baseline_pairs'],
            'datasets':protocol['datasets'],'protocol_sha256':hashlib.sha256(raw).hexdigest(),'implementation_hashes':hashes,
            'runtime_source_bundle':runtime,'stress_multiplier':2,'risk_matched_to_strategy':False,'parameter_selection_allowed':False,
            'live_promotion_allowed':False}
        budget=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
        sha=ledger.register(manifest,protocol_id=budget,maximum_per_family=protocol['search_limits']['max_configurations_per_family'],protocol_version=protocol['protocol_version'])
        receipt={'study_sha256':sha,'manifest':json.loads(json.dumps(manifest,default=str))}
        path=directory/sha/'protocol.json'
        if path.exists():
            if json.loads(path.read_bytes())!=receipt:raise ValueError('existing context receipt changed')
        else:write_json_report(path,receipt)
        print(json.dumps({'registered_study':sha,'receipt':str(path),'reserved_contexts':1}));return
    receipt=json.loads(args.receipt.read_bytes());manifest=receipt['manifest'];sha=receipt['study_sha256']
    if identity(manifest)!=sha:raise ValueError('registered context changed')
    assert_source_dependencies(manifest['implementation_hashes'],dependencies())
    load_runtime_sources(manifest['runtime_source_bundle'],manifest['implementation_hashes'])
    if hashlib.sha256((ROOT/'config/research-protocol-v1.json').read_bytes()).hexdigest()!=manifest['protocol_sha256']:raise ValueError('source protocol changed')
    protocol=prepare_research();candidate=manifest['grid'][0];prior=ledger.result(sha,candidate)
    if prior is None:
        started=datetime.now(UTC)
        data={pair:ArchiveReader(ROOT/'.local/archive',protocol=protocol).read_candles(pair,limit=5000)[:3500] for pair in manifest['pairs']}
        if any(len(rows)!=3500 for rows in data.values()):raise ValueError('complete declared context slice required')
        source=_save_raw(directory/'inputs',json.dumps({pair:[asdict(row) for row in rows] for pair,rows in data.items()},sort_keys=True,default=str).encode())
        prior={'parameters':candidate,'study_sha256':sha,'execution_started_at':started.isoformat(),
            'ordinary':buy_hold_context(data,cfg,entry_index=120),
            'stress':buy_hold_context(data,cfg.stress_costs(2),entry_index=120),'input_snapshot':source,
            'execution_finished_at':datetime.now(UTC).isoformat(),'live_promotion_allowed':False}
        assert_source_dependencies(manifest['implementation_hashes'],dependencies());ledger.record(sha,candidate,prior)
    report={'study_sha256':sha,'manifest':manifest,'results':[prior],'completed_configurations':1,'live_promotion_allowed':False}
    output=args.receipt.with_name('results.json')
    if output.exists():
        if json.loads(output.read_bytes())!=report:raise ValueError('original context report changed')
    else:write_json_report(output,report)
    print(json.dumps({'completed_contexts':1,'risk_matched_to_strategy':False,'live_promotion_allowed':False}))


if __name__=='__main__':main()
