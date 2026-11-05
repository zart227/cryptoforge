"""Real fixed subprocesses on synthetic unit data; no operational admissions."""
from copy import deepcopy
import subprocess
import sys
import threading

import pytest

from cryptoforge import training_fit_reuse_worker as worker
from test_training_fit_reuse import EVIDENCE, inputs


def run(tmp_path, **kwargs):
    data, protocol, configs = inputs(tmp_path)
    return worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=lambda *a: None, **kwargs)


def capture_processes(monkeypatch, replacement=None):
    actual = subprocess.Popen; processes = []; invocations = []
    def launch(argv, **kwargs):
        invocations.append((argv, kwargs))
        process = actual(replacement if replacement is not None else argv, **kwargs)
        processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    return processes, invocations


def test_real_worker_matches_independent_primitive_and_checks_kernel_limits(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []
    expected = worker.reuse.evaluate_admitted_batch(data, protocol, configs, evidence_context=EVIDENCE, admit=lambda *a: None)
    monkeypatch.setenv('CRYPTOFORGE_OPENROUTER_API_KEY', 'synthetic-secret-must-not-leak')
    monkeypatch.setenv('OTHER_PRIVATE_VALUE', 'synthetic-private-environment')
    processes, calls = capture_processes(monkeypatch)
    # The trusted child imports source afresh; parent must never optimize/predict.
    for name in ('fit_standardizer', 'fit_logistic_head', 'predict_probability'):
        monkeypatch.setattr(worker.reuse.planner.model_training, name, lambda *a, **k: pytest.fail('parent model work forbidden'))
    result = worker.run(data, protocol, configs, evidence_context=EVIDENCE,
        admit=lambda evaluation, context: charges.append((evaluation['logical_evaluation_key'], context)))
    assert result['worker']['result'] == expected and len(charges) == 7
    assert result['worker']['result']['actual_counts']['long_head_fits'] == 4
    assert not result['existing_budget_adapter_used'] and not result['operational_study_approved']
    argv, options = calls[0]
    assert argv == [sys.executable, '-B', '-m', 'cryptoforge.training_fit_reuse_worker', '--worker']
    assert set(options['env']) == {'PATH', 'LANG', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE'}
    assert options['stderr'] == subprocess.DEVNULL and options['start_new_session'] and options['close_fds']
    assert 'synthetic-secret' not in repr(argv) + repr(options['env'])
    assert options['stdin'].closed and options['stdout'].closed and all(p.poll() is not None for p in processes)
    usage = result['worker']['usage']
    assert usage['rlimits']['cpu'] == [10, 10] and usage['rlimits']['address_space'] == [268435456, 268435456]
    assert usage['rlimits']['file_size'] == [2000000, 2000000] and usage['rlimits']['core'] == [0, 0]
    assert usage['nice'] >= 10 and 0 < usage['maximum_rss_kib'] <= 262144
    # A retained synthetic receipt, never a permission or real source manifest.
    p = tmp_path/'synthetic-worker-equivalence.json'
    p.write_text(worker.canonical({'only_synthetic_unit_data': True, 'data': data, 'protocol': protocol,
        'configurations': configs, 'evidence_context': EVIDENCE, 'execution': result,
        'exact_primitive_result_sha256': worker.digest(expected), 'operational_model_actions': 0}))
    p.chmod(0o600)


def test_all_admissions_finish_before_exactly_one_launch(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []
    actual = subprocess.Popen; launches = []
    def launch(*a, **k):
        assert charges == list(range(7)); launches.append(1); return actual(*a, **k)
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=lambda e, c: charges.append(e['index']))
    assert len(launches) == 1


def test_partial_admission_failure_keeps_prior_charges_and_launches_nothing(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []
    def admit(e, context):
        if e['index'] == 3: raise ValueError('synthetic allowance exhausted')
        charges.append(e['index'])
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('no launch'))
    with pytest.raises(ValueError, match='exhausted'):
        worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=admit)
    assert charges == [0, 1, 2]


@pytest.mark.parametrize('stage', ['before', 'during_admission', 'after_launch'])
def test_cancellation_before_during_and_after_launch_is_terminal(tmp_path, monkeypatch, stage):
    data, protocol, configs = inputs(tmp_path); cancel = threading.Event(); charges = []; processes = []
    actual = subprocess.Popen
    if stage == 'before': cancel.set()
    def admit(e, context):
        charges.append(e['index'])
        if stage == 'during_admission': cancel.set()
    def launch(*a, **k):
        assert stage == 'after_launch'; p = actual(*a, **k); processes.append(p); cancel.set(); return p
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    with pytest.raises(worker.BudgetCancelled):
        worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=admit, cancel_event=cancel)
    assert len(charges) == {'before': 0, 'during_admission': 1, 'after_launch': 7}[stage]
    assert all(p.poll() is not None for p in processes)


def test_real_deadline_kills_and_reaps_without_refund_or_retry(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []
    processes, _ = capture_processes(monkeypatch, [sys.executable, '-c', 'import time; time.sleep(30)'])
    with pytest.raises(worker.BudgetTimedOut):
        worker.run(data, protocol, configs, evidence_context=EVIDENCE,
            admit=lambda e, c: charges.append(e['index']), wall_seconds=.05)
    assert charges == list(range(7)) and len(processes) == 1 and processes[0].poll() is not None


@pytest.mark.parametrize('code', ['raise SystemExit(2)', 'print("private malformed reply")',
    'import sys; sys.stdout.write("x"*2000001)'])
def test_nonzero_malformed_and_oversized_worker_results_never_retry(tmp_path, monkeypatch, code):
    processes, calls = capture_processes(monkeypatch, [sys.executable, '-c', code])
    with pytest.raises(ValueError) as error: run(tmp_path)
    assert 'private malformed reply' not in str(error.value)
    assert len(calls) == 1 and all(p.poll() is not None for p in processes)


@pytest.mark.parametrize('field', ['batch_hash', 'counts', 'binding', 'artifact_hash', 'configuration',
    'threshold', 'row_count', 'development_end', 'approval_flag', 'stds'])
def test_changed_result_or_attestation_is_refused_without_rerunning_models(tmp_path, field):
    data, protocol, configs = inputs(tmp_path)
    result = worker.reuse.evaluate_admitted_batch(data, protocol, configs, evidence_context=EVIDENCE, admit=lambda *a: None)
    expected = deepcopy(result['plan'])
    if field == 'batch_hash': result['batch_sha256'] = 'f'*64
    elif field == 'counts': result['actual_counts']['long_head_fits'] = 3
    elif field == 'binding': result['result_bindings'][0]['fit_key'] = 'f'*64
    elif field == 'artifact_hash': result['results'][0]['artifact_sha256'] = 'f'*64
    elif field == 'configuration': result['results'][0]['artifact']['config']['threshold'] = .7
    elif field == 'threshold': result['results'][0]['reports']['validation']['diagnostics']['decision_threshold'] = .7
    elif field == 'row_count': result['results'][0]['reports']['validation']['diagnostics']['evidence']['overall']['count'] = 19
    elif field == 'development_end': result['results'][0]['artifact']['fit_information_end'] = '2025-01-03T00:00:00+00:00'
    elif field == 'approval_flag': result['external_budgets_or_approval_attested'] = True
    else: result['results'][0]['artifact']['stds'][0] = 0.
    if field not in ('batch_hash', 'artifact_hash'):
        result['results'][0]['artifact_sha256'] = worker.digest(result['results'][0]['artifact'])
    if field != 'batch_hash': result['batch_sha256'] = worker.digest({k: v for k, v in result.items() if k != 'batch_sha256'})
    with pytest.raises(ValueError): worker._check_result(result, expected, protocol['development_end'])


@pytest.mark.parametrize('change', ['source', 'protocol', 'config', 'false_admit', 'wall_limit', 'no_admit'])
def test_invalid_input_or_source_changes_cannot_launch(tmp_path, monkeypatch, change):
    data, protocol, configs = inputs(tmp_path); admit = lambda *a: None; extra = {}
    if change == 'source': monkeypatch.setattr(worker, 'implementation', lambda: {})
    elif change == 'protocol': protocol['epochs'] = 0
    elif change == 'config': configs[0]['threshold'] = .99
    elif change == 'false_admit': admit = lambda *a: False
    elif change == 'wall_limit': extra['wall_seconds'] = 21
    else: admit = None
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('invalid invocation cannot launch'))
    with pytest.raises(ValueError): worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=admit, **extra)


def test_caller_mutations_during_admission_cannot_change_captured_inputs(tmp_path):
    data, protocol, configs = inputs(tmp_path); evidence = deepcopy(EVIDENCE)
    expected = worker.reuse.plan(data, protocol, configs, evidence_context=evidence)
    def admit(e, context):
        data['train'][0]['features'][0] = 999.; protocol['epochs'] = 100
        configs[0]['l2'] = 1.; evidence['raw_source_manifest_sha256'] = 'f'*64; e['configuration']['l2'] = 99.
    result = worker.run(data, protocol, configs, evidence_context=evidence, admit=admit)
    assert result['worker']['result']['plan'] == expected


def test_source_change_during_admission_refuses_before_child_launch(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []
    def admit(e, context):
        charges.append(e['index']); monkeypatch.setattr(worker, 'implementation', lambda: {})
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('changed worker cannot launch'))
    with pytest.raises(ValueError, match='changed'):
        worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=admit)
    assert charges == [0]


def test_launch_failure_keeps_all_admissions_and_does_not_retry(tmp_path, monkeypatch):
    data, protocol, configs = inputs(tmp_path); charges = []; launches = []
    def fail(*a, **k): launches.append(1); raise OSError('synthetic launch failure')
    monkeypatch.setattr(worker.subprocess, 'Popen', fail)
    with pytest.raises(OSError):
        worker.run(data, protocol, configs, evidence_context=EVIDENCE, admit=lambda e, c: charges.append(e['index']))
    assert charges == list(range(7)) and len(launches) == 1


def test_worker_receipt_type_resource_source_and_request_tampering_is_refused(tmp_path):
    # This tests validation using a real synthetic child receipt, without new
    # model work for any of the altered receipts below.
    execution = run(tmp_path); original = execution['worker']; result = original['result']
    data, protocol, configs = inputs(tmp_path)
    request = {'schema_version': 'fixed-fit-reuse-worker-request-v1', 'implementation': deepcopy(worker._LOADED),
        'policy': deepcopy(worker.POLICY), 'data': data, 'protocol': protocol, 'configurations': configs,
        'evidence_context': EVIDENCE, 'plan_sha256': worker.digest(result['plan'])}
    assert worker._check_envelope(original, request, result['plan']) == original
    for change in ('request', 'implementation', 'policy', 'cpu', 'rss', 'rlimit', 'environment', 'count_bool'):
        changed = deepcopy(original)
        if change == 'request': changed['request_sha256'] = 'f'*64
        elif change == 'implementation': changed['implementation']['worker'] = 'f'*64
        elif change == 'policy': changed['policy']['nice_increment'] = True
        elif change == 'cpu': changed['usage'].update(cpu_user_seconds=9., cpu_system_seconds=9.)
        elif change == 'rss': changed['usage']['maximum_rss_kib'] = 999999
        elif change == 'rlimit': changed['usage']['rlimits']['core'] = [False, False]
        elif change == 'environment': changed['usage']['environment_keys'].append('PRIVATE_VALUE')
        else:
            changed['result']['actual_counts']['standardizer_fits'] = True
            changed['result']['batch_sha256'] = worker.digest({k: v for k, v in changed['result'].items() if k != 'batch_sha256'})
        with pytest.raises(ValueError): worker._check_envelope(changed, request, result['plan'])


def test_worker_has_no_persistent_cache_or_implicit_journal_writes(tmp_path, monkeypatch):
    processes, calls = capture_processes(monkeypatch)
    for _ in (1, 2): run(tmp_path)
    assert len(calls) == 2 and all(p.poll() is not None for p in processes)
    assert not list(tmp_path.glob('*.sqlite')) and not list(tmp_path.glob('*.claim'))
