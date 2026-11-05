"""Bind original venue reference revisions to development audits, without data admission."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_data_protocol as temporal, research_local_export as private
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import semantic_source_collector as files
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields


POLICY = {'schema_version': 'research-revision-bridge-policy-v1', 'maximum_database_bytes': 8388608,
    'maximum_events': 128, 'maximum_versions': 1024, 'maximum_delivered_rows': 2048,
    'maximum_projection_bytes': 1048576, 'worker_wall_seconds': 15,
    'worker_cpu_seconds': 8, 'worker_memory_bytes': 536870912, 'worker_file_bytes': 2097152,
    'training_admission_enabled': False,
    'reviewed_package_init_sha256': 'b86a73500010a249293fdddaee182c18773a0b942f2d0d919718b73456fe2bd6',
    'reviewed_sources': {
        'reference_sources.py': 'cb2342f59721be44e8169499b45341e685f00b1ba9c7aeae66c4e8f1df0fff17',
        'reference_source_ledger.py': '9836b7db0016c585bd6c7d2cc39e50bea77ca10736cddd5c7104ee0cfe9dc1fa',
        'local_source_provenance.py': '555f3c4e130b940e1ba5a8411edd0a5b19f1e62771dee2aab997c4e579537bd8',
        'local_source_observer.py': '96391942abfc4a1390fd11dd26777a06a144f9e887c95195dc279c635afcf8f3',
        'backend.py': 'ee3ce91d461871e4710ad00fdfbd8ebe8f7d0bb2ccb6ba8876ee55d45d0c9c61',
        'model_training.py': '9afb8aab375ec786aa8f9c9a7f617a5db642e49fcfbf45d311a413a05e63aeb7',
        'supabase_executor.py': 'b3a8530632498fc1291f1eecd2aae085b58fc6f4bc2a4b8c89c5bfcf4eb1910c',
        'capture_reference_sources.py': '7749db8cd160e0db1e32a494620f2110b1a38e84a69376962596d36f08c7d070',
        'audit_local_source_provenance.py': 'cabece8162092a5002ee289a1b763ec5f98d75d53e4fa15f946e08a91e019691'}}
FLAGS = ('source_poll_completeness_verified', 'historical_known_at_verified',
    'full_worker_or_host_qualified', 'paper_evidence_pass', 'economic_profitability_established',
    'live_admission_granted', 'counts_as_real_executed_buys')


def implementation():
    return {'bridge': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker': hashlib.sha256(Path(__file__).with_name('research_revision_worker.py').read_bytes()).hexdigest(),
        'temporal_audit': temporal.implementation()}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY): raise ValueError('fixed_revision_bridge_policy_required')
    if implementation() != _LOADED: raise ValueError('revision_bridge_source_changed_restart_required')


def main_profile(project):
    project = private._safe_directory(project)
    init = project/'src/cryptoforge/__init__.py'
    if init.is_symlink() or hashlib.sha256(init.read_bytes()).hexdigest() != POLICY['reviewed_package_init_sha256']:
        raise ValueError('reviewed_main_package_init_required')
    profile = {}
    for name in POLICY['reviewed_sources']:
        path = project / ('scripts' if name in ('capture_reference_sources.py', 'audit_local_source_provenance.py') else 'src/cryptoforge') / name
        private._safe_directory(path.parent)
        profile[name] = hashlib.sha256(reviewed_main.reviewed_source_bytes(project, name)).hexdigest()
    if profile != POLICY['reviewed_sources']: raise ValueError('main_reference_runtime_requires_review')
    return profile


def _reference(reference, project=None):
    exact_fields(reference, {'root', 'manifest_sha256', 'registration_sha256', 'database_sha256', 'head_sha256'})
    for key, value in reference.items():
        if key != 'root': temporal._sha(value)
    if type(reference['root']) is not str or len(reference['root']) > 4096: raise ValueError('bounded_reference_root_required')
    root = private._safe_directory(reference['root'], private=True)
    if root.resolve() != root or str(root) != reference['root']: raise ValueError('canonical_original_reference_root_required')
    if project is not None and not root.is_relative_to(Path(project)/'.local'):
        raise ValueError('original_project_research_namespace_required')
    if {p.name for p in root.iterdir()} != {'manifest.json', 'registered.json', 'writer.lock', 'source.sqlite'}:
        raise ValueError('source_only_original_namespace_required')
    maximums = {'manifest.json': 64000, 'registered.json': 4000, 'writer.lock': 0,
                'source.sqlite': POLICY['maximum_database_bytes']}
    raws = {name: private._private_read(root, name, maximum) for name, maximum in maximums.items()}
    for name, key in (('manifest.json', 'manifest_sha256'), ('registered.json', 'registration_sha256'), ('source.sqlite', 'database_sha256')):
        if hashlib.sha256(raws[name]).hexdigest() != reference[key]: raise ValueError('original_reference_pin_mismatch')
    manifest = files.strict_json(raws['manifest.json'].decode(), max_bytes=64000)
    if manifest.get('artifact_sha256') is not None: raise ValueError('source_only_ledger_without_model_required')
    if manifest.get('runtime') != POLICY['reviewed_sources']: raise ValueError('original_reference_runtime_requires_review')
    return manifest


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (POLICY['worker_cpu_seconds'], POLICY['worker_cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (POLICY['worker_memory_bytes'], POLICY['worker_memory_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (POLICY['worker_file_bytes'], POLICY['worker_file_bytes']))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def _project(project, reference, protocol, directory):
    packet = {'reference': reference,
        'maximum_close_ms': int(temporal._time(protocol['validation_information_end']).timestamp()*1000),
        'holdout_start_ms': int(temporal._time(protocol['partitions']['final_test']['decision_start']).timestamp()*1000)}
    files._write(directory, 'packet.json', packet)
    worker = Path(__file__).with_name('research_revision_worker.py')
    args = [sys.executable, '-B', str(worker), '--input', str(directory/'packet.json'), '--output', str(directory/'projection.json')]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
           'LANG': 'C.UTF-8', 'TZ': 'UTC', 'PYTHONHASHSEED': '0'}
    proc = None
    with os.fdopen(os.open(directory/'worker.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as output:
        try:
            proc = subprocess.Popen(args, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=output,
                stderr=output, start_new_session=True, preexec_fn=_limits)
            if proc.wait(timeout=POLICY['worker_wall_seconds']) != 0: raise ValueError('native_reference_projection_refused')
            return temporal._read(directory, 'projection.json', POLICY['maximum_projection_bytes'])
        finally:
            if proc is not None:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait()


def validate_projection(projection, protocol, context):
    exact_fields(projection, {'schema_version', 'reference', 'source_manifest', 'native_audit', 'rows', 'polls',
        'loaded_source_hashes', 'source_database_modified', 'network_request_performed',
        'forecast_or_inference_performed', 'native_scratch_redirected_to_private_worker_directory'})
    if (projection['schema_version'] != 'research-reference-projection-v1'
            or projection['loaded_source_hashes'] != POLICY['reviewed_sources']
            or any(projection[k] is not False for k in ('source_database_modified', 'network_request_performed', 'forecast_or_inference_performed'))
            or projection['native_scratch_redirected_to_private_worker_directory'] is not True
            or len(canonical(projection).encode()) > POLICY['maximum_projection_bytes']):
        raise ValueError('fixed_source_only_native_projection_required')
    exact_fields(context, {'schema_version', 'audited_at'})
    if context['schema_version'] != 'research-revision-context-v1': raise ValueError('revision_context_required')
    now = temporal._time(context['audited_at'])
    intervals = temporal.validate_protocol(protocol, context['audited_at'])
    manifest, audit = projection['source_manifest'], projection['native_audit']
    exact_fields(manifest, {'mode', 'registered_at', 'start', 'end', 'pairs', 'mandatory_pairs'})
    if (manifest['mode'] not in ('diagnostic', 'prospective') or manifest['mandatory_pairs'] != ['BTC/USDT', 'ETH/USDT']
            or type(manifest['pairs']) is not list or not 2 <= len(manifest['pairs']) <= 4
            or any(type(p) is not str or re.fullmatch('[A-Z0-9]{1,24}/USDT', p) is None for p in manifest['pairs'])
            or not set(manifest['mandatory_pairs']).issubset(manifest['pairs'])
            or sorted(p.replace('/', '') for p in manifest['pairs']) != protocol['symbols']):
        raise ValueError('explicit_reference_pair_scope_required')
    if not temporal._time(manifest['registered_at']) <= now or not temporal._time(manifest['start']) < temporal._time(manifest['end']):
        raise ValueError('source_registration_times_required')
    exact_fields(audit, {'events_checked', 'versions_checked', 'forecasts_checked', 'latest_status',
        'source_trace_integrity_pass', 'original_source_forecast_linkage_pass', 'scope', *FLAGS})
    if (any(type(audit[k]) is not int or not 0 <= audit[k] <= POLICY[limit] for k, limit in
            (('events_checked', 'maximum_events'), ('versions_checked', 'maximum_versions')))
            or type(audit['forecasts_checked']) is not int or audit['forecasts_checked'] != 0 or audit['source_trace_integrity_pass'] is not True
            or audit['original_source_forecast_linkage_pass'] is not False or audit['scope'] != manifest['mode']
            or any(audit[k] is not False for k in FLAGS)):
        raise ValueError('source_trace_integrity_is_not_admission')
    if type(projection['polls']) is not list or len(projection['polls']) > 32 or type(projection['rows']) is not list or len(projection['rows']) > POLICY['maximum_delivered_rows']:
        raise ValueError('bounded_reference_history_required')
    responses, previous_anchor = {}, None
    for poll_index, poll in enumerate(projection['polls']):
        exact_fields(poll, {'anchor_ms', 'completed_at', 'responses'})
        anchor = poll['anchor_ms']
        if (type(anchor) is not int or anchor % 300000 or previous_anchor is not None and anchor <= previous_anchor
                or not temporal._time(manifest['start']) <= temporal._time(poll['completed_at']) <= min(now, temporal._time(manifest['end']))
                or type(poll['responses']) is not list or [r.get('pair') for r in poll['responses']] != manifest['pairs']):
            raise ValueError('ordered_complete_original_polls_required')
        previous_anchor = anchor
        if datetime.fromtimestamp(anchor/1000, timezone.utc) > temporal._time(protocol['validation_information_end']):
            raise ValueError('source_after_development_information_cutoff')
        for response_index, response in enumerate(poll['responses']):
            exact_fields(response, {'pair', 'event_seq', 'sha256', 'status', 'known_at', 'recorded_at', 'latest_close_ms', 'rows'})
            seq = response['event_seq']; temporal._sha(response['sha256'])
            expected_seq = poll_index*(2+len(manifest['pairs']))+response_index+2
            if type(seq) is not int or seq != expected_seq or seq in responses or response['status'] not in ('ready', 'stale', 'unavailable', 'invalid'):
                raise ValueError('source_response_identity_required')
            if not temporal._time(response['recorded_at']) <= temporal._time(poll['completed_at']): raise ValueError('response_after_poll_completion')
            if response['known_at'] is not None and temporal._time(response['known_at']) > temporal._time(response['recorded_at']): raise ValueError('response_observation_after_recording')
            expected_rows = 120 if response['status'] in ('ready', 'stale') else 0
            if type(response['rows']) is not int or response['rows'] != expected_rows: raise ValueError('complete_reference_response_rows_required')
            if expected_rows and (response['known_at'] is None or response['latest_close_ms'] != anchor): raise ValueError('closed_reference_anchor_required')
            if expected_rows:
                age = temporal._time(response['known_at']).timestamp()*1000-anchor
                if response['status'] != ('ready' if 0 <= age <= 600000 else 'stale'): raise ValueError('original_source_freshness_status_mismatch')
            responses[seq] = (response, anchor, poll['completed_at'])
    if audit['events_checked'] != len(projection['polls'])*(2+len(manifest['pairs'])): raise ValueError('all_source_events_must_be_projected')
    latest = {r['pair']: r['status'] for r in projection['polls'][-1]['responses']} if projection['polls'] else {}
    if audit['latest_status'] != latest: raise ValueError('latest_source_status_mismatch')
    seen, versions, counts, timeline = set(), {}, {}, []
    for row in projection['rows']:
        exact_fields(row, {'source_id', 'version_sha256', 'pair', 'open_ms', 'observed_at', 'first_seen_at', 'event_seq', 'response_sha256'})
        for key in ('source_id', 'version_sha256', 'response_sha256'): temporal._sha(row[key])
        if row['event_seq'] not in responses: raise ValueError('row_missing_original_response')
        response, anchor, poll_completed = responses[row['event_seq']]
        if (row['pair'] != response['pair'] or row['observed_at'] != response['known_at'] or row['response_sha256'] != response['sha256']
                or type(row['open_ms']) is not int or row['open_ms'] % 300000 or not anchor-120*300000 <= row['open_ms'] < anchor):
            raise ValueError('row_response_scope_or_time_mismatch')
        natural = {'provider': 'https://api.bybit.com', 'path': '/v5/market/kline', 'category': 'spot',
                   'pair': row['pair'], 'interval': '5', 'open_ms': row['open_ms']}
        if row['source_id'] != digest(natural): raise ValueError('venue_natural_source_id_mismatch')
        key = (row['event_seq'], row['source_id'])
        if key in seen: raise ValueError('duplicate_delivered_reference_row')
        seen.add(key); counts[row['event_seq']] = counts.get(row['event_seq'], 0)+1
        version = (row['source_id'], row['version_sha256'])
        versions.setdefault(version, []).append(row)
        opened = datetime.fromtimestamp(row['open_ms']/1000, timezone.utc)
        closed = opened+timedelta(minutes=5)
        if closed > temporal._time(row['observed_at']) or closed > intervals['final_test'][0]: raise ValueError('closed_development_source_only')
        timeline.append({'symbol': row['pair'].replace('/', ''), 'open_time': opened.isoformat(),
            'close_time': closed.isoformat(), 'known_at': poll_completed,
            'observed_at': row['observed_at'], 'first_seen_at': row['first_seen_at'],
            'source_id': row['source_id'], 'revision_sha256': row['version_sha256'],
            'source_sha256': row['response_sha256']})
    if any(counts.get(seq, 0) != response['rows'] for seq, (response, _, _) in responses.items()): raise ValueError('projected_reference_row_coverage_mismatch')
    if len(versions) != audit['versions_checked']: raise ValueError('all_first_seen_versions_required')
    for rows in versions.values():
        first = min(temporal._time(r['observed_at']) for r in rows)
        if any(temporal._time(r['first_seen_at']) != first for r in rows): raise ValueError('original_first_seen_cannot_be_rewritten')
    timeline.sort(key=lambda r: (r['symbol'], r['open_time'], r['known_at'], r['revision_sha256']))
    return intervals, timeline


def audit(projection, protocol, exposure, context, policy=POLICY):
    _guard(policy)
    intervals, timeline = validate_projection(projection, protocol, context)
    temporal.validate_exposures(exposure, protocol, context['audited_at'])
    index = {}
    for row in timeline: index.setdefault((row['symbol'], row['open_time']), []).append(row)
    step = timedelta(minutes=5); samples = []
    for partition, next_partition, cutoff_key in (('train', 'validation', 'fit_information_end'), ('validation', 'final_test', 'validation_information_end')):
        start, end = intervals[partition]; cutoff = temporal._time(protocol[cutoff_key])
        for symbol in protocol['symbols']:
            anchor = start
            while anchor < end:
                decision = anchor+timedelta(seconds=protocol['decision_delay_seconds'])
                label_end = anchor+3*step; issues = set(); selected = []
                for name, opens, limit in (('feature', [anchor-(120-i)*step for i in range(120)], decision),
                                          ('label', [anchor+i*step for i in range(3)], cutoff)):
                    chosen = []
                    for opened in opens:
                        row, error = temporal._choose(index, symbol, opened, limit)
                        if error: issues.add(name+'_'+error)
                        else: chosen.append(row)
                    selected.append(chosen)
                delivered = [p for p in projection['polls'] if temporal._time(p['completed_at']) <= decision]
                latest = delivered[-1] if delivered else None
                if (latest is None or any(r['status'] != 'ready' or r['known_at'] is None
                        or not 0 <= (decision-temporal._time(r['known_at'])).total_seconds() <= 600
                        or not 0 <= decision.timestamp()*1000-r['latest_close_ms'] <= 600000 for r in latest['responses'])):
                    issues.add('mandatory_reference_unavailable_or_stale')
                if label_end >= intervals[next_partition][0]: issues.add('label_crosses_next_partition_purge')
                if label_end > cutoff: issues.add('label_not_complete_by_information_cutoff')
                features, labels = selected
                samples.append({'partition': partition, 'symbol': symbol, 'decision_anchor': anchor.isoformat(),
                    'decision_time': decision.isoformat(), 'label_end_time': label_end.isoformat(),
                    'feature_rows_available': len(features), 'label_rows_available': len(labels),
                    'feature_lineage_sha256': digest(features) if len(features) == 120 else None,
                    'label_lineage_sha256': digest(labels) if len(labels) == 3 else None,
                    'metadata_consistency_pass': not issues, 'issues': sorted(issues)})
                anchor += step
    counts = {}
    for sample in samples:
        for issue in sample['issues']: counts[issue] = counts.get(issue, 0)+1
    source_exposures = [{'symbol': r['pair'].replace('/', ''),
        'start': datetime.fromtimestamp((p['anchor_ms']-120*300000)/1000, timezone.utc).isoformat(),
        'end': datetime.fromtimestamp(p['anchor_ms']/1000, timezone.utc).isoformat(),
        'kind': 'market_values_observed', 'source_sha256': r['sha256']}
        for p in projection['polls'] for r in p['responses'] if r['rows']]
    core = {'schema_version': 'research-revision-audit-v1', 'status': 'blocked' if counts else 'metadata_consistent',
        'source_domain': 'bybit_spot_reference_http', 'audited_at': context['audited_at'],
        'projection_sha256': digest(projection), 'protocol_sha256': digest(protocol), 'exposure_sha256': digest(exposure),
        'context_sha256': digest(context), 'policy_sha256': digest(policy), 'source_reference': projection['reference'],
        'source_mode': projection['source_manifest']['mode'], 'native_audit': projection['native_audit'],
        'observed_deliveries': len(timeline), 'unique_versions': projection['native_audit']['versions_checked'],
        'timeline_sha256': digest(timeline), 'samples': samples, 'sample_count': len(samples),
        'samples_metadata_consistent': sum(s['metadata_consistency_pass'] for s in samples), 'sample_issue_counts': dict(sorted(counts.items())),
        'source_exposures_recorded_automatically': source_exposures,
        'selection_rule': 'latest_completed_poll_delivery_not_first_seen_version_order',
        'original_first_seen_preserved': True, 'venue_ids_are_postgresql_uuids': False,
        'protocol_registration_authenticated': False, 'exposure_inventory_complete': False,
        'source_features_labels_parity_verified': False, 'training_data_admitted': False,
        'training_executed': False, 'forecast_or_inference_performed': False, 'network_request_performed': False,
        'production_promotion_authorized': False, **{k: False for k in FLAGS}, 'implementation': deepcopy(_LOADED)}
    result = {**core, 'audit_sha256': digest(core)}
    if len(canonical(result).encode()) > temporal.POLICY['max_report_bytes']: raise ValueError('revision_audit_report_byte_limit')
    _guard(policy)
    return result


def prepare(directory, project, reference, protocol, exposure):
    _guard(POLICY); directory = Path(directory).absolute(); project = private._safe_directory(project)
    private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_revision_audit_directory_required')
    context = {'schema_version': 'research-revision-context-v1', 'audited_at': datetime.now(timezone.utc).isoformat()}
    temporal.validate_protocol(protocol, context['audited_at']); temporal.validate_exposures(exposure, protocol, context['audited_at'])
    before = main_profile(project); _reference(reference, project)
    with tempfile.TemporaryDirectory(prefix='reference-projection-', dir=directory.parent) as tmp:
        projection = _project(project, reference, protocol, Path(tmp))
    if main_profile(project) != before: raise ValueError('main_reference_runtime_changed_during_audit')
    _reference(reference, project)
    if projection['reference'] != reference: raise ValueError('projection_reference_mismatch')
    report = audit(projection, protocol, exposure, context)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('projection.json', projection), ('protocol.json', protocol),
                        ('exposure.json', exposure), ('context.json', context), ('audit.json', report)):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent)
    return report


def verify(directory):
    directory = private._safe_directory(directory, private=True)
    policy = temporal._read(directory, 'policy.json', 16000)
    protocol, exposure, context = (temporal._read(directory, n+'.json', 64000) for n in ('protocol', 'exposure', 'context'))
    projection = temporal._read(directory, 'projection.json', POLICY['maximum_projection_bytes'])
    _reference(projection['reference'])
    report = audit(projection, protocol, exposure, context, policy)
    if canonical(report) != canonical(temporal._read(directory, 'audit.json', temporal.POLICY['max_report_bytes'])):
        raise ValueError('revision_audit_or_implementation_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        cmd = subs.add_parser(name); cmd.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            for arg in ('project', 'reference', 'protocol', 'exposure'): cmd.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = verify(args.directory) if args.command == 'verify' else prepare(args.directory, args.project,
            *[temporal._read(getattr(args, n).parent, getattr(args, n).name, 64000) for n in ('reference', 'protocol', 'exposure')])
    except Exception:
        print('Revision source audit refused; training admission disabled'); return 2
    print('Revision source audit verified: '+report['status']+'; training admission disabled'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
