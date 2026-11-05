"""Fixed resource-bounded executor for the ephemeral long-head batch primitive.

All logical admissions remain caller-owned. This module does not open journals,
verify source manifests, approve data or grant any new study/budget allowance.
It runs trusted installed code only, never generated Python or command text.
"""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from cryptoforge import training_fit_reuse as reuse
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_run_budget import BudgetCancelled, BudgetTimedOut
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, number, validate_diagnostics


POLICY = {'schema_version': 'fixed-fit-reuse-worker-v1', 'cpu_seconds': 10,
    'address_space_bytes': 256 * 1024 * 1024, 'wall_seconds': 20, 'cleanup_seconds': 1,
    'maximum_input_bytes': 20_000_000, 'maximum_output_bytes': 2_000_000,
    'nice_increment': 10, 'persistent_cache': False, 'journal_writes': False,
    'generated_code_execution': False, 'network_namespace_enforced': False,
    'whole_server_resource_bound': False, 'study_or_budget_approval_attested': False}


def implementation():
    return {'worker': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'primitive': reuse.implementation()}


_LOADED = implementation()
_POLICY = canonical(POLICY)


def _guard():
    reuse._guard()
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fit_batch_worker_source_or_policy_changed')


def _cancel(event):
    if event is not None and event.is_set(): raise BudgetCancelled('fit batch cancelled')


def _deadline(deadline):
    if time.monotonic() >= deadline: raise BudgetTimedOut('fit batch local deadline exceeded')


def _check_result(result, expected, development_end):
    """Check the worker receipt without repeating optimization or predictions."""
    exact_fields(result, {'schema_version', 'plan', 'results', 'result_bindings', 'actual_counts',
        'persistent_model_cache_reused', 'logical_evaluation_charges_reduced',
        'external_budgets_or_approval_attested', 'production_compatible', 'batch_sha256'})
    if (result['schema_version'] != 'fit-reuse-batch-result-v1' or canonical(result['plan']) != canonical(expected)
            or canonical(result['actual_counts']) != canonical(expected['counts'])
            or any(result[k] is not False for k in ('persistent_model_cache_reused',
                'logical_evaluation_charges_reduced', 'external_budgets_or_approval_attested', 'production_compatible'))
            or digest({k: v for k, v in result.items() if k != 'batch_sha256'}) != result['batch_sha256']):
        raise ValueError('fit_batch_result_or_context_mismatch')
    n = len(expected['evaluations'])
    if type(result['results']) is not list or len(result['results']) != n:
        raise ValueError('fit_batch_result_coverage_mismatch')
    bindings = []
    for evaluation, item in zip(expected['evaluations'], result['results'], strict=True):
        exact_fields(item, {'artifact', 'artifact_sha256', 'reports'})
        artifact = item['artifact']; context = expected['context']
        exact_fields(artifact, {'schema_version', 'family', 'target_version', 'feature_version',
            'feature_names', 'weights', 'bias', 'means', 'stds', 'config', 'fit_information_end', 'production_compatible'})
        if (artifact['schema_version'] != 'offline-long-head-v1'
                or artifact['family'] != reuse.planner.model_training.MODEL_FAMILY
                or artifact['target_version'] != context['target_version']
                or artifact['feature_version'] != context['feature_version']
                or artifact['feature_names'] != context['feature_names']
                or canonical(artifact['config']) != canonical(evaluation['configuration'])
                or artifact['fit_information_end'] != development_end
                or artifact['production_compatible'] is not False or digest(artifact) != item['artifact_sha256']):
            raise ValueError('fit_batch_artifact_mismatch')
        for name in ('weights', 'means', 'stds'):
            values = artifact[name]
            if type(values) is not list or len(values) != len(context['feature_names']):
                raise ValueError('fit_batch_vector_shape_mismatch')
            for value in values:
                number(value, -1e100, 1e100)
                if name == 'stds' and value <= 0: raise ValueError('fit_batch_positive_scale_required')
        number(artifact['bias'], -1e100, 1e100)
        exact_fields(item['reports'], {'train', 'validation'})
        for partition, report in item['reports'].items():
            exact_fields(report, {'diagnostics', 'selected_observations', 'selected_positive_rate'})
            diagnostics = validate_diagnostics(report['diagnostics'])
            if (diagnostics['partition'] != partition or diagnostics['dataset_sha256'] != context['dataset_sha256']
                    or diagnostics['source_sha256'] != digest(context['implementation']['planner'])
                    or diagnostics['development_end'] != development_end
                    or diagnostics['decision_threshold'] != evaluation['configuration']['threshold']
                    or diagnostics['evidence']['overall']['count'] != context['training_rows' if partition == 'train' else 'validation_rows']):
                raise ValueError('fit_batch_diagnostics_mismatch')
            count = report['selected_observations']
            if type(count) is not int or not 0 <= count <= context['training_rows' if partition == 'train' else 'validation_rows']:
                raise ValueError('fit_batch_selection_count_mismatch')
            if count == 0:
                if report['selected_positive_rate'] is not None: raise ValueError('empty_selection_rate_must_be_null')
            else: number(report['selected_positive_rate'], 0, 1)
        bindings.append({'logical_evaluation_key': evaluation['logical_evaluation_key'],
            'context_sha256': expected['context_sha256'], 'fit_key': evaluation['fit_key'],
            'prediction_key': evaluation['prediction_key'], 'artifact_sha256': item['artifact_sha256'],
            'reports_sha256': digest(item['reports'])})
    if result['result_bindings'] != bindings: raise ValueError('fit_batch_result_binding_mismatch')
    return result


def _check_envelope(envelope, request, expected):
    exact_fields(envelope, {'schema_version', 'implementation', 'policy', 'request_sha256', 'result', 'usage'})
    if (envelope['schema_version'] != 'fixed-fit-reuse-worker-result-v1' or envelope['implementation'] != _LOADED
            or canonical(envelope['policy']) != _POLICY or envelope['request_sha256'] != digest(request)):
        raise ValueError('fit_batch_worker_receipt_mismatch')
    _check_result(envelope['result'], expected, request['protocol']['development_end'])
    usage = envelope['usage']
    exact_fields(usage, {'cpu_user_seconds', 'cpu_system_seconds', 'maximum_rss_kib', 'nice', 'rlimits', 'environment_keys'})
    for name in ('cpu_user_seconds', 'cpu_system_seconds'): number(usage[name], 0, POLICY['cpu_seconds'])
    if (usage['cpu_user_seconds'] + usage['cpu_system_seconds'] > POLICY['cpu_seconds']
            or type(usage['maximum_rss_kib']) is not int or not 0 < usage['maximum_rss_kib'] <= POLICY['address_space_bytes'] // 1024
            or type(usage['nice']) is not int or usage['nice'] < POLICY['nice_increment']
            or canonical(usage['rlimits']) != canonical({'cpu': [POLICY['cpu_seconds']] * 2,
                'address_space': [POLICY['address_space_bytes']] * 2,
                'file_size': [POLICY['maximum_output_bytes']] * 2, 'core': [0, 0]})
            or usage['environment_keys'] != ['LANG', 'PATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH']):
        raise ValueError('fit_batch_resource_receipt_mismatch')
    return envelope


def run(data, protocol, configurations, *, evidence_context, admit, wall_seconds=20, cancel_event=None):
    """Admit every logical evaluation, then launch exactly one bounded worker.

    ``admit`` is the same caller-owned callback seam as M57, not a permission
    check. A real budget adapter and original-manifest verification are still
    required before operational use. There is no automatic retry or refund.
    """
    _cancel(cancel_event); _guard()
    wall_seconds = number(wall_seconds, .001, POLICY['wall_seconds'])
    if not callable(admit): raise ValueError('explicit_logical_admission_callback_required')
    data, protocol, configurations, evidence_context = deepcopy((data, protocol, configurations, evidence_context))
    expected = reuse.plan(data, protocol, configurations, evidence_context=evidence_context)
    request = {'schema_version': 'fixed-fit-reuse-worker-request-v1', 'implementation': deepcopy(_LOADED),
        'policy': deepcopy(POLICY), 'data': data, 'protocol': protocol, 'configurations': configurations,
        'evidence_context': evidence_context, 'plan_sha256': digest(expected)}
    raw = canonical(request).encode()
    if len(raw) > POLICY['maximum_input_bytes']: raise ValueError('bounded_fit_batch_input_required')
    for evaluation in expected['evaluations']:
        _cancel(cancel_event)
        if admit(deepcopy(evaluation), expected['context_sha256']) is not None:
            raise ValueError('admission_callback_must_return_none_or_raise')
        _guard()
    _cancel(cancel_event)
    env = {'LANG': 'C.UTF-8', 'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    # Anonymous private files prevent pipe buffering from growing with output.
    # Child RLIMIT_FSIZE also bounds stdout at the kernel, before parent reads.
    process = None
    with tempfile.TemporaryFile(dir='/tmp') as incoming, tempfile.TemporaryFile(dir='/tmp') as outgoing:
        incoming.write(raw); incoming.flush(); incoming.seek(0)
        deadline = time.monotonic() + wall_seconds; started = time.monotonic()
        try:
            process = subprocess.Popen([sys.executable, '-B', '-m', 'cryptoforge.training_fit_reuse_worker', '--worker'],
                stdin=incoming, stdout=outgoing, stderr=subprocess.DEVNULL, env=env,
                cwd=Path(__file__).resolve().parents[2], start_new_session=True, close_fds=True)
            while True:
                _cancel(cancel_event); _deadline(deadline)
                try:
                    process.wait(timeout=min(.02, max(.0001, deadline-time.monotonic()))); break
                except subprocess.TimeoutExpired:
                    if os.fstat(outgoing.fileno()).st_size > POLICY['maximum_output_bytes']:
                        raise ValueError('bounded_fit_batch_output_required')
            _cancel(cancel_event); _deadline(deadline); _guard()
            if process.returncode != 0: raise ValueError('fit_batch_worker_failed_or_resource_limit')
            outgoing.seek(0); body = outgoing.read(POLICY['maximum_output_bytes'] + 1)
            if len(body) > POLICY['maximum_output_bytes']: raise ValueError('bounded_fit_batch_output_required')
            envelope = _check_envelope(strict_json(body.decode(), max_bytes=POLICY['maximum_output_bytes']), request, expected)
            _cancel(cancel_event); _deadline(deadline); _guard()
            return {'schema_version': 'fixed-fit-reuse-execution-v1', 'worker': envelope,
                'parent_worker_wall_seconds': time.monotonic()-started, 'wall_limit_seconds': wall_seconds,
                'cleanup_grace_seconds': POLICY['cleanup_seconds'], 'logical_admission_callbacks': len(expected['evaluations']),
                'existing_budget_adapter_used': False, 'original_manifests_verified': False,
                'operational_study_approved': False, 'production_compatible': False}
        except KeyboardInterrupt:
            raise BudgetCancelled('fit batch interrupted') from None
        finally:
            if process is not None:
                if process.poll() is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                process.wait(timeout=POLICY['cleanup_seconds'])


def _worker():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (POLICY['cpu_seconds'],) * 2)
    resource.setrlimit(resource.RLIMIT_AS, (POLICY['address_space_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (POLICY['maximum_output_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.nice(POLICY['nice_increment'])
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, POLICY['wall_seconds'])
    request = strict_json(sys.stdin.buffer.read(POLICY['maximum_input_bytes'] + 1).decode(), max_bytes=POLICY['maximum_input_bytes'])
    exact_fields(request, {'schema_version', 'implementation', 'policy', 'data', 'protocol',
        'configurations', 'evidence_context', 'plan_sha256'})
    _guard()
    if (request['schema_version'] != 'fixed-fit-reuse-worker-request-v1' or request['implementation'] != _LOADED
            or canonical(request['policy']) != _POLICY): raise ValueError('fixed_fit_batch_request_required')
    expected = reuse.plan(request['data'], request['protocol'], request['configurations'], evidence_context=request['evidence_context'])
    if digest(expected) != request['plan_sha256']: raise ValueError('parent_child_fit_plan_mismatch')
    # These are internal consistency checks, not manufactured budget receipts.
    def checked(evaluation, context):
        if context != expected['context_sha256'] or evaluation != expected['evaluations'][evaluation['index']]:
            raise ValueError('fit_batch_logical_identity_mismatch')
    result = reuse.evaluate_admitted_batch(request['data'], request['protocol'], request['configurations'],
        evidence_context=request['evidence_context'], admit=checked)
    _guard(); _check_result(result, expected, request['protocol']['development_end'])
    usage = resource.getrusage(resource.RUSAGE_SELF)
    envelope = {'schema_version': 'fixed-fit-reuse-worker-result-v1', 'implementation': _LOADED,
        'policy': POLICY, 'request_sha256': digest(request), 'result': result,
        'usage': {'cpu_user_seconds': usage.ru_utime, 'cpu_system_seconds': usage.ru_stime,
            'maximum_rss_kib': usage.ru_maxrss, 'nice': os.getpriority(os.PRIO_PROCESS, 0),
            'rlimits': {name: list(resource.getrlimit(kind)) for name, kind in (
                ('cpu', resource.RLIMIT_CPU), ('address_space', resource.RLIMIT_AS),
                ('file_size', resource.RLIMIT_FSIZE), ('core', resource.RLIMIT_CORE))},
            'environment_keys': sorted(os.environ)}}
    body = canonical(envelope).encode()
    if len(body) > POLICY['maximum_output_bytes']: raise ValueError('bounded_fit_batch_output_required')
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()


if __name__ == '__main__':
    if sys.argv[1:] != ['--worker']: raise SystemExit('internal fixed fit batch worker only')
    try: _worker()
    except Exception: raise SystemExit('fixed fit batch worker rejected input') from None
