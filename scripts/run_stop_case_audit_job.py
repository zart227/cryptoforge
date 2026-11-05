"""Resume a fixed minute audit, rejecting changed inputs or implementations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, UTC
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.source_contract import assert_source_dependencies, source_hashes
from cryptoforge.training_snapshot import load_runtime_sources, save_runtime_sources
from cryptoforge.intrabar_source_audit import compare_intrabar_source
from cryptoforge.intrabar_audit import audit_barrier_order
from cryptoforge.archive import ArchiveReader
from cryptoforge.execution_market_evidence import _load

ROOT = Path(__file__).resolve().parents[1]


def dependencies():
    return {'compare': compare_intrabar_source, 'barrier': audit_barrier_order,
            'reader': ArchiveReader, 'runner': ROOT/'scripts/audit_stop_case_minutes.py',
            'supervisor': Path(__file__).resolve()}


def verify_report(report, job, receipt):
    if report['original_ingestion_receipt'] != receipt['receipt']:
        raise ValueError('foreign ingestion evidence')
    ingestion = _load(receipt['receipt'])
    expected = {case['case_id']: case['source_sample']['pair'] for case in ingestion['cases']}
    actual = {case['case_id']: case['pair'] for case in report['cases']}
    if (len(expected) != ingestion['selected_case_count'] or actual != expected
            or len(report['cases']) != len(expected) or report['completed_cases'] != len(expected)):
        raise ValueError('complete unique selected cases required')
    if report['source_report_sha256'] != ingestion['source_report_sha256']:
        raise ValueError('foreign original source report')
    hashes = {key: value for key, value in job['implementation_hashes'].items() if key != 'supervisor'}
    if report['implementation_hashes'] != hashes:
        raise ValueError('foreign audit implementation')
    load_runtime_sources(report['runtime_source_bundle'], hashes)
    for key in ('real_fill_certified', 'historical_observation_time_certified',
                'trade_policy_changed', 'live_promotion_allowed'):
        if report[key] is not False:
            raise ValueError('diagnostic scope changed')


def run(path):
    status = {'observed_at': datetime.now(UTC).isoformat(), 'completed': False,
              'live_promotion_allowed': False}
    try:
        job = json.loads(path.read_bytes())
        assert_source_dependencies(job['implementation_hashes'], dependencies())
        load_runtime_sources(job['runtime_source_bundle'], job['implementation_hashes'])
        raw = Path(job['ingestion']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != job['ingestion_sha256']:
            raise ValueError('fixed ingestion pointer changed')
        receipt = json.loads(raw)
        profile=job.get('resource_protocol')
        if profile and hashlib.sha256(Path(profile).read_bytes()).hexdigest()!=job['resource_protocol_sha256']:
            raise ValueError('fixed resource profile changed')
        output = Path(job['output'])
        if not output.exists():
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/audit_stop_case_minutes.py'),
                '--ingestion', job['ingestion'], '--output', job['output']]+(['--resource-protocol',profile] if profile else []), cwd=ROOT,
                capture_output=True, text=True, timeout=135,
                env={**os.environ, 'PYTHONPATH': str(ROOT/'src'), 'PYTHONDONTWRITEBYTECODE': '1'})
            if proc.returncode:
                raise ValueError('audit process failed: '+proc.stderr[-1000:])
            if not output.exists():
                child = json.loads(output.with_name(output.stem+'-status.json').read_bytes())
                if child['status'] != 'deferred_resource_or_worker_guard' or child['completed']:
                    raise ValueError('missing complete output')
                status['status'] = child['status']
                write_json_report(path.with_name('status.json'), status)
                return status
        verify_report(json.loads(output.read_bytes()), job, receipt)
        status.update(status='completed', completed=True,
                      report_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    except Exception as exc:
        status.update(status='blocked_contract_or_audit', error_class=type(exc).__name__, error=str(exc))
    write_json_report(path.with_name('status.json'), status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--freeze-ingestion', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resource-protocol',type=Path)
    args = parser.parse_args()
    if args.freeze_ingestion:
        if args.job.exists() or args.output is None:
            parser.error('new job and explicit output required')
        deps = dependencies(); hashes = source_hashes(deps)
        write_json_report(args.job, {'observed_at': datetime.now(UTC).isoformat(),
            'ingestion': str(args.freeze_ingestion.resolve()),
            'ingestion_sha256': hashlib.sha256(args.freeze_ingestion.read_bytes()).hexdigest(),
            'output': str(args.output.resolve()), 'implementation_hashes': hashes,
            'resource_protocol':str(args.resource_protocol.resolve()) if args.resource_protocol else None,
            'resource_protocol_sha256':hashlib.sha256(args.resource_protocol.read_bytes()).hexdigest() if args.resource_protocol else None,
            'runtime_source_bundle': save_runtime_sources(args.job.parent/'runtime', deps, hashes)})
    print(json.dumps(run(args.job)))


if __name__ == '__main__':
    main()
