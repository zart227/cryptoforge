import copy
from datetime import datetime, timedelta, timezone
import json
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor

import pytest

from cryptoforge import model_training
from cryptoforge.training_diagnostics import digest
from cryptoforge.training_experiment_planner import (
    freeze_protocol, load_development, run_experiment, ledger_lock,
)
from cryptoforge.llm_training_experiment_cli import main


def dataset(tmp_path):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    def rows(day):
        return [{'pair': 'BTC/USDT', 'open_time': (start+timedelta(days=day, minutes=i*5)).isoformat(),
                 'label_end_time': (start+timedelta(days=day, minutes=i*5+1)).isoformat(),
                 'features': [((i%2)*2-1)*0.1 + j*0.01 for j in range(7)], 'label': i%2}
                for i in range(20)]
    data = {'schema_version': 'llm-development-examples-v1', 'target_version': 'fixed-future-return-v1',
            'feature_version': model_training.FEATURE_VERSION, 'feature_names': list(model_training.FEATURE_NAMES),
            'train': rows(0), 'validation': rows(1)}
    path = tmp_path/'development.json'
    path.write_text(json.dumps(data))
    return path, data


def proposal(parameter='l2', value=0.1):
    return {'schema_version': 'llm-training-proposal-v1', 'hypothesis_id': 'check-l2',
            'evidence_ids': ['overall'], 'rationale': 'Check stability.',
            'expected_effect': 'Lower development loss.', 'falsification': 'Reject if loss increases.',
            'parameter': parameter, 'value': value}


def setup(tmp_path, maximum=4):
    path, data = dataset(tmp_path)
    protocol = freeze_protocol(path, version='synthetic-v1', maximum=maximum, epochs=5)
    ledger = tmp_path/'attempts.sqlite'
    baseline = run_experiment(path, protocol, ledger)
    report = baseline['reports']['validation']['diagnostics']
    return path, data, protocol, ledger, baseline, report


def test_real_fit_and_repeat_use_same_immutable_artifact(tmp_path, monkeypatch):
    path, _, protocol, ledger, baseline, report = setup(tmp_path)
    assert baseline['training_executed'] and not baseline['cached']
    assert baseline['artifact']['production_compatible'] is False
    assert set(baseline['reports']) == {'train', 'validation'}
    assert baseline['artifact']['fit_information_end'] == protocol['development_end']
    def no_fit(*args, **kwargs):
        raise AssertionError('repeat must not fit')
    monkeypatch.setattr(model_training, 'fit_logistic_head', no_fit)
    repeat = run_experiment(path, protocol, ledger)
    assert repeat['cached'] and not repeat['training_executed']
    assert repeat['artifact_sha256'] == baseline['artifact_sha256']


def test_candidate_applies_parameter_and_hypothesis_rename_cannot_spend_again(tmp_path):
    path, _, protocol, ledger, baseline, report = setup(tmp_path)
    candidate = run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    assert candidate['artifact']['config']['l2'] == 0.1
    assert candidate['budget_usage'] == {'llm-offline-long-head-v1': 2}
    changed = proposal()
    changed.update(hypothesis_id='different-text', rationale='Another description.')
    repeat = run_experiment(path, protocol, ledger, proposal=changed, report=report)
    assert repeat['cached'] and repeat['study_id'] == candidate['study_id']


def test_persistent_budget_survives_new_runner(tmp_path):
    path, _, protocol, ledger, _, report = setup(tmp_path, maximum=1)
    with pytest.raises(ValueError, match='budget exhausted'):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(test=d['validation']),
    lambda d: d['train'][0].update(label_end_time=d['validation'][0]['open_time']),
    lambda d: d['validation'][0].update(features=[0]*6),
    lambda d: d['train'][0].update(features=[float('nan')]*7),
    lambda d: d['train'][0].update(api_key='secret'),
    lambda d: d.update(target_version='cash-result-v1'),
])
def test_development_boundary_and_contracts(mutation, tmp_path):
    path, data = dataset(tmp_path)
    mutation(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_development(path)


def test_frozen_protocol_rejects_data_mutation_before_registering(tmp_path):
    path, data = dataset(tmp_path)
    protocol = freeze_protocol(path, version='fixed', epochs=5)
    data['validation'][0]['label'] = 1
    path.write_text(json.dumps(data))
    ledger = tmp_path/'attempts.sqlite'
    with pytest.raises(ValueError, match='identity changed'):
        run_experiment(path, protocol, ledger)
    assert not ledger.exists()


def test_unregistered_and_forged_reports_cannot_drive_search(tmp_path):
    path, _, protocol, ledger, _, report = setup(tmp_path)
    report['evidence']['overall']['brier_score'] = 0.9
    with pytest.raises(ValueError, match='not registered evidence'):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    assert not (tmp_path/'missing.sqlite').exists()
    with pytest.raises(ValueError, match='registered validation evidence'):
        run_experiment(path, protocol, tmp_path/'missing.sqlite', proposal=proposal(), report=report)


def test_history_change_not_silently_treated_as_sample_count(tmp_path):
    path, _, protocol, ledger, _, report = setup(tmp_path)
    with pytest.raises(ValueError, match='raw candle rebuild'):
        run_experiment(path, protocol, ledger, proposal=proposal('lookback_candles', 500), report=report)


def test_failed_fit_is_recorded_and_never_automatically_retried(tmp_path, monkeypatch):
    path, _, protocol, ledger, _, report = setup(tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError('private exception details')
    import cryptoforge.training_experiment_planner as planner
    monkeypatch.setattr(planner, 'execute_fit', fail)
    with pytest.raises(RuntimeError):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    with pytest.raises(ValueError, match='prior failed attempt'):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    with sqlite3.connect(ledger) as db:
        payload = db.execute("SELECT payload FROM attempts WHERE status='failed'").fetchone()[0]
    assert 'private exception' not in payload


def _try_lock(path):
    try:
        with ledger_lock(path):
            return 'acquired'
    except ValueError:
        return 'blocked'


def test_concurrent_process_cannot_run_same_ledger(tmp_path):
    path = tmp_path/'attempts.sqlite'
    # Create process before acquiring lock so it does not inherit the descriptor.
    import multiprocessing
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
        with ledger_lock(path):
            assert pool.submit(_try_lock, path).result(timeout=10) == 'blocked'
        assert pool.submit(_try_lock, path).result(timeout=10) == 'acquired'


def test_crash_claim_blocks_silent_refit(tmp_path):
    path, _, protocol, ledger, _, report = setup(tmp_path)
    # Simulate crash after reservation and claim, before completion.
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE attempts SET status='reserved',payload=NULL")
    with pytest.raises(ValueError, match='interrupted reserved attempt'):
        run_experiment(path, protocol, ledger)


def test_freeze_and_run_cli_without_network(tmp_path):
    path, _ = dataset(tmp_path)
    protocol, output, ledger = (tmp_path/name for name in ('protocol.json', 'result.json', 'attempts.sqlite'))
    assert main(['--dataset', str(path), '--output', str(protocol), 'freeze', '--version', 'cli-v1', '--epochs', '5']) == 0
    assert main(['--dataset', str(path), '--output', str(output), 'run', '--protocol', str(protocol), '--ledger', str(ledger)]) == 0
    result = json.loads(output.read_text())['result']
    assert result['training_executed'] and not result['cached']
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_complete_mock_advice_to_registered_candidate_cli(tmp_path):
    from cryptoforge.llm_training_research_cli import main as advise
    path, _ = dataset(tmp_path)
    protocol, baseline, ledger, mock, advice, candidate = (tmp_path/name for name in
        ('protocol.json', 'baseline.json', 'attempts.sqlite', 'mock.json', 'advice.json', 'candidate.json'))
    assert main(['--dataset', str(path), '--output', str(protocol), 'freeze', '--version', 'chain-v1', '--epochs', '5']) == 0
    run_args = ['run', '--protocol', str(protocol), '--ledger', str(ledger)]
    assert main(['--dataset', str(path), '--output', str(baseline), *run_args]) == 0
    mock.write_text(json.dumps(proposal()))
    assert advise(['--experiment-receipt', str(baseline), '--mock-response', str(mock), '--output', str(advice)]) == 0
    assert main(['--dataset', str(path), '--output', str(candidate), *run_args, '--advice-receipt', str(advice)]) == 0
    result = json.loads(candidate.read_text())['result']
    assert result['artifact']['config']['l2'] == 0.1
    assert result['budget_usage'] == {'llm-offline-long-head-v1': 2}


def test_worker_timeout_is_sanitized_and_failed_attempt_persists(tmp_path, monkeypatch):
    import subprocess
    import cryptoforge.training_experiment_planner as planner
    path, _, protocol, ledger, _, report = setup(tmp_path)
    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == 20
        assert set(kwargs['env']) == {'PYTHONPATH', 'LANG', 'PATH'}
        raise subprocess.TimeoutExpired(args[0], 20)
    monkeypatch.setattr(planner.subprocess, 'run', timeout)
    with pytest.raises(ValueError, match='wall-time limit'):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)
    with pytest.raises(ValueError, match='prior failed attempt'):
        run_experiment(path, protocol, ledger, proposal=proposal(), report=report)


def test_development_snapshot_saved_privately_and_tampering_blocks_reuse(tmp_path):
    from pathlib import Path
    path, _, protocol, ledger, baseline, _ = setup(tmp_path)
    snapshot = Path(baseline['development_snapshot']['path'])
    assert snapshot.stat().st_mode & 0o777 == 0o600
    saved = json.loads(snapshot.read_text())
    assert set(saved) == {'schema_version', 'target_version', 'feature_version', 'feature_names', 'train', 'validation'}
    assert digest(saved) == protocol['dataset_sha256']
    snapshot.write_text('{}')
    with pytest.raises(ValueError, match='content-address mismatch'):
        run_experiment(path, protocol, ledger)
