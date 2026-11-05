"""Reconstruct an exploratory dataset from an already captured source pack.

No network, model fitting, inference, publication, approval, or budget change.
The result is wrapped as review-only and is not a planner dataset on its own.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_source_diagnostics as source
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import training_experiment_planner as planner
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version':'review-source-dataset-policy-v1', 'validation_hours':6,
    'embargo_minutes':15, 'timeframe_minutes':5, 'maximum_input_bytes':20_000_000,
    'maximum_output_bytes':8_000_000, 'worker_wall_seconds':60,
    'retrospective_snapshot_only':True, 'training_admission_enabled':False,
    'model_fit_prediction_publication_enabled':False}
WORKER = Path(__file__).resolve().parents[2]/'scripts/replay_source_dataset_worker.py'


def implementation():
    return {'builder':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker':hashlib.sha256(WORKER.read_bytes()).hexdigest(),
        'source':source.implementation(), 'planner':planner.implementation_hashes()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    source._guard()
    if implementation()!=_LOADED or canonical(POLICY)!=_POLICY: raise ValueError('source_dataset_implementation_changed')


def _read(directory, name, cap=8_000_000):
    return source.source.prior.late.cohort.values.temporal._read(directory, name, cap)


def _inputs(directory):
    _guard()
    directory = source.source.prior.late.cohort.values.private._safe_directory(directory, private=True)
    diagnostics = source.verify(directory); binding = _read(directory, 'binding.json', 262144)
    pack = Path(binding['source_pack']); audit = source.source.verify(pack)
    captured, rows, _, _ = source.source.inspect_capture(pack/'captures')
    native = _read(pack, 'native.json', 524288); pack_binding = _read(pack, 'binding.json', 262144)
    if (diagnostics['capture_sha256'] != digest(captured) or diagnostics['source_audit_sha256'] != audit['audit_sha256']
            or native['capture_sha256'] != digest(captured) or native['as_of'] != captured['completed_at']):
        raise ValueError('same_original_source_diagnostics_required')
    packet_rows = {}
    for pair, values in rows.items():
        packet_rows[pair] = [{k:(str(v) if k in source.source.wire.NUMERIC else v) for k,v in row.items()} for row in values]
    packet = {'schema_version':'source-dataset-replay-request-v1','worker_sha256':_LOADED['worker'],
        'module_hashes':native['loaded_value_runtime'],'pairs':source.POLICY['pairs'],
        'as_of':captured['completed_at'],'rows':packet_rows}
    return {'diagnostics_directory':str(directory), 'diagnostics_sha256':diagnostics['report_sha256'],
        'source_pack':str(pack), 'source_audit_sha256':audit['audit_sha256'], 'capture_sha256':digest(captured),
        'native_examples_sha256':native['native']['all_examples_sha256'], 'main_project':pack_binding['project']}, diagnostics, audit, native, packet


def _replay(project, packet):
    raw = canonical(packet).encode()
    if len(raw)>POLICY['maximum_input_bytes']: raise ValueError('bounded_replay_packet_required')
    project = Path(project).resolve(); process = None
    env = {'PATH':os.defpath, 'PYTHONPATH':reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE':'1',
        'PYTHONHASHSEED':'0', 'LANG':'C.UTF-8', 'TZ':'UTC'}
    with tempfile.TemporaryFile(dir='/tmp') as incoming, tempfile.TemporaryFile(dir='/tmp') as output:
        incoming.write(raw); incoming.flush(); incoming.seek(0)
        try:
            process = subprocess.Popen([sys.executable,'-B',str(WORKER)], cwd=project, env=env,
                stdin=incoming, stdout=output, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
            try: process.wait(timeout=POLICY['worker_wall_seconds'])
            except subprocess.TimeoutExpired: raise ValueError('source_replay_deadline_exceeded_no_retry') from None
            if process.returncode != 0: raise ValueError('source_replay_worker_failed_no_retry')
            output.seek(0); result = output.read(POLICY['maximum_output_bytes']+1)
            if len(result)>POLICY['maximum_output_bytes']: raise ValueError('bounded_replay_result_required')
            return strict_json(result.decode(), max_bytes=POLICY['maximum_output_bytes'])
        finally:
            if process is not None:
                if process.poll() is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                process.wait(timeout=1)


def _checked_replay(result, native, packet):
    exact_fields(result, {'schema_version','request_sha256','examples','examples_sha256','source_admission',
        'main_runtime_hashes','query_pairs','network_fit_prediction_publication_performed'})
    if (result['schema_version']!='source-dataset-replay-result-v1' or result['request_sha256']!=digest(packet)
            or result['examples_sha256']!=digest(result['examples'])
            or result['examples_sha256']!=native['native']['all_examples_sha256']
            or result['examples_sha256']!=native['exact_parser']['all_examples_sha256']
            or len(result['examples'])!=native['native']['all_examples']
            or canonical(result['source_admission'])!=canonical(native['native']['source_admission'])
            or result['main_runtime_hashes']!=native['loaded_value_runtime'] or result['query_pairs']!=packet['pairs']
            or result['network_fit_prediction_publication_performed'] is not False):
        raise ValueError('original_native_full_example_replay_mismatch')
    return result


def _split(rows, as_of):
    """A fixed exploratory split, after the source had already been observed."""
    cutoff = timestamp(as_of); aligned = cutoff.replace(minute=cutoff.minute-cutoff.minute%5, second=0, microsecond=0)
    start = aligned-timedelta(hours=POLICY['validation_hours']); embargo = start-timedelta(minutes=POLICY['embargo_minutes'])
    train=[]; validation=[]; purged=0
    for row in rows:
        exact_fields(row, {'pair','input_end_time','label_end_time','feature_hex','future_return_hex','long_label','short_label'})
        opened=timestamp(row['input_end_time']); end=timestamp(row['label_end_time'])
        if not opened < end <= cutoff or type(row['long_label']) is not int or row['long_label'] not in (0,1):
            raise ValueError('bounded_original_label_information_required')
        if type(row['feature_hex']) is not list or len(row['feature_hex']) != len(planner.model_training.FEATURE_NAMES):
            raise ValueError('original_feature_vector_shape_required')
        try: features=[float.fromhex(x) for x in row['feature_hex']]
        except (ValueError,TypeError): raise ValueError('original_binary64_feature_required') from None
        if any(not math.isfinite(v) or abs(v)>1e6 for v in features): raise ValueError('bounded_original_feature_required')
        item={'pair':row['pair'],'open_time':opened.isoformat(),'label_end_time':end.isoformat(),
            'features':features,'label':row['long_label']}
        if opened >= start: validation.append(item)
        elif end < embargo: train.append(item)
        else: purged+=1
    candidate={'schema_version':planner.DATA_VERSION,'target_version':'fixed-future-return-v1',
        'feature_version':planner.model_training.FEATURE_VERSION,'feature_names':list(planner.model_training.FEATURE_NAMES),
        'train':train,'validation':validation}
    planner.parse_development(candidate)
    return candidate, {'validation_start':start.isoformat(), 'train_label_end_before':embargo.isoformat(),
        'source_capture_cutoff':cutoff.isoformat(), 'train_examples':len(train),'validation_examples':len(validation),
        'purged_examples':purged,'embargo_minutes':POLICY['embargo_minutes'],
        'train_positive_labels':sum(row['label'] for row in train),'validation_positive_labels':sum(row['label'] for row in validation)}


def _assemble(binding, diagnostics, audit, native, packet, replay):
    _checked_replay(replay, native, packet)
    candidate, split = _split(replay['examples'], packet['as_of'])
    core={'schema_version':'review-only-source-dataset-v1','implementation':_LOADED,'policy_sha256':digest(POLICY),
        'binding':binding,'source_diagnostics_sha256':diagnostics['report_sha256'],
        'source_proposal_route':diagnostics['proposal_route'],'source_blocking_reasons':diagnostics['source_blocking_reasons'],
        'source_coverage':diagnostics['coverage'],'full_native_examples_sha256':replay['examples_sha256'],
        'split':split,'candidate_dataset_sha256':digest(candidate),'candidate_dataset':candidate,
        'training_admitted':False,'historical_first_seen_revision_lineage_verified':False,
        'independent_holdout_or_prospective_study':False,'provider_proposals_authorized':False,
        'model_fit_prediction_publication_performed':False,'numeric_budget_change_or_new_allowance':False}
    return {**core,'review_sha256':digest(core)}


def prepare(directory, diagnostics_directory):
    _guard(); directory=Path(directory).absolute()
    source.source.prior.late.cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_review_directory_required_no_retry')
    binding, diagnostics, audit, native, packet = _inputs(diagnostics_directory)
    replay = _replay(binding['main_project'],packet); _guard()
    if _inputs(diagnostics_directory)!=(binding,diagnostics,audit,native,packet): raise ValueError('original_source_changed_during_replay')
    report=_assemble(binding,diagnostics,audit,native,packet,replay)
    directory.mkdir(mode=0o700)
    write=source.source.prior.late.cohort.values.files._write
    for name,value in (('policy.json',POLICY),('binding.json',binding),('native-replay.json',replay),('review.json',report)):
        write(directory,name,value)
    return report


def verify(directory):
    _guard(); directory=source.source.prior.late.cohort.values.private._safe_directory(directory,private=True)
    if _read(directory,'policy.json',262144)!=POLICY: raise ValueError('original_review_policy_changed')
    saved=_read(directory,'binding.json',262144)
    binding, diagnostics, audit, native, packet = _inputs(saved['diagnostics_directory'])
    if binding!=saved: raise ValueError('original_source_binding_changed')
    report=_assemble(binding,diagnostics,audit,native,packet,_read(directory,'native-replay.json'))
    if report!=_read(directory,'review.json'): raise ValueError('original_review_dataset_changed')
    return report
