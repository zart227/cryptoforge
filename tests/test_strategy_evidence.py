from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from cryptoforge.cash_study_paths import load_cash_study
from cryptoforge.cash_study_registry import CashStudyRegistry
from cryptoforge.live_learning_protocol import time
from cryptoforge.model_training import predict_probability
from cryptoforge.paper_acceptance import AcceptanceRegistry, evaluate_paper
from cryptoforge.paper_policy_design import validate_execution_design
from cryptoforge.paper_results import export_results
from cryptoforge.paper_runtime import paper_runtime_hashes
from cryptoforge.paper_wallet import PaperWallet
from cryptoforge.paper_worker import PaperWorker
from cryptoforge.prospective_shadow import ShadowLedger
from cryptoforge.strategy_evidence import audit_strategy_evidence, canonical, digest, EvidenceFiles
from test_paper_wallet import Clock, market


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return raw


def collection(tmp_path):
    protocol = json.loads(Path('config/live-cash-recovery-closed-protocol-v1.json').read_bytes())
    protocol['protocol_version'] = 'synthetic-provenance-unit-test'
    path = tmp_path / 'protocol.json'
    raw = write(path, protocol)
    path.with_suffix('.sha256').write_text(digest(raw))
    state = tmp_path / 'state'
    CashStudyRegistry(state / 'cash-study-registry.sqlite',
        clock=lambda: time(protocol['frozen_at'])).freeze(raw)
    _, study = load_cash_study(path, state_root=state)
    return path, protocol, state, study


def complete(tmp_path):
    path, protocol, state, study = collection(tmp_path)
    selected = time(protocol['windows']['validation']['end_exclusive']) + timedelta(hours=1)
    artifact = dict(model_family='pure-python-logistic', selected_l2=.01,
        feature_version='candle-v1', trained_at=selected.isoformat(), live_eligible=False,
        threshold=.5, feature_names=['return_1', 'return_3', 'range_12', 'volume_ratio',
            'ema_gap', 'rsi_14', 'candle_body'], weights=[1.] + [0.] * 6,
        means=[0.] * 7, stds=[1.] * 7, bias=0., config=dict(
            target_version=protocol['target_version'], input_candle_state='closed_only',
            fit_information_end=(selected-timedelta(days=2)).isoformat(),
            feature_input_contract=protocol['feature_input_contract']))
    artifact_path = study.root / 'synthetic-model.json'
    model_sha = digest(write(artifact_path, artifact))
    manifest = dict(protocol_version=protocol['protocol_version'],
        protocol_sha256=study.protocol_sha256, selected_at=selected.isoformat(),
        threshold='0.50', live_eligible=False, artifact_path=str(artifact_path), artifact_sha256=model_sha)
    manifest_raw = write(study.candidate, manifest)
    ledger = ShadowLedger(study.predictions, clock=lambda: selected)
    ledger.freeze_candidate(manifest_raw, registered_at=selected)
    policy = json.loads(Path('config/paper-execution-policy-v1.json').read_bytes())
    policy.update(protocol_version=protocol['protocol_version'], status='frozen', enabled=True,
        implementation_hashes=paper_runtime_hashes())
    policy_raw = write(study.execution_policy, policy)
    receipt = ledger.freeze_paper_policy(policy_raw, protocol_sha=study.protocol_sha256, candidate_sha=model_sha)
    write(study.execution_policy.with_suffix('.freeze.json'), receipt)
    acceptance = json.loads(Path('config/paper-acceptance-policy-v1.json').read_bytes())
    acceptance.update(protocol_version=protocol['protocol_version'], minimum_buys=2,
        minimum_entry_days=2, minimum_pairs=1, bootstrap_block_days=2, bootstrap_repetitions=100,
        maximum_pair_fraction='1', maximum_entry_day_fraction='1',
        maximum_mark_gap_seconds=31*86400, maximum_endpoint_gap_seconds=1)
    acceptance_raw = write(study.acceptance_policy, acceptance)
    receipt = AcceptanceRegistry(study.acceptance_registry, clock=lambda: selected).freeze(
        acceptance_raw, protocol_sha=study.protocol_sha256)
    write(study.acceptance_policy.with_suffix('.freeze.json'), receipt)
    start = time(protocol['windows']['paper']['start']) + timedelta(seconds=protocol['embargo_seconds'])
    end = time(protocol['windows']['paper']['end_exclusive'])
    clock = Clock()
    clock.now = start
    workers = {}
    for role in ('candidate', 'baseline_control', 'stress_candidate'):
        config = validate_execution_design(policy)
        role_policy = deepcopy(policy)
        role_policy['evaluation_role'] = role
        if role == 'stress_candidate':
            multiplier = Decimal(acceptance['stress_cost_multiplier'])
            config = replace(config, entry_fee=config.entry_fee*multiplier,
                exit_fee=config.exit_fee*multiplier, slippage=config.slippage*multiplier,
                cost_assumption_id=config.cost_assumption_id+':stress-x'+str(multiplier))
            role_policy['wallet'] = {**role_policy['wallet'], **{key: str(getattr(config, key))
                for key in ('entry_fee', 'exit_fee', 'slippage', 'cost_assumption_id')}}
        wallet_path, worker_path = study.paper_role_paths(role)
        wallet = PaperWallet(wallet_path, candidate_sha=model_sha, config=config, clock=clock)
        worker = PaperWorker(wallet, worker_path, policy=role_policy, clock=clock,
            market=lambda pair: market(clock, pair, step='.00000001'),
            exit_indicator=lambda pair: (True, []))
        workers[role] = worker
    for index, (feature, exit_price) in enumerate(((1., '110'), (-1., '95')) * 2):
        clock.now = start + timedelta(days=index//2, hours=(index%2)*2)
        features = [feature] + [0.] * 6
        probability = predict_probability(features, artifact['weights'], artifact['bias'], artifact['means'], artifact['stds'])
        ledger.clock = clock
        ledger.record(candidate_sha=model_sha, opportunity='op'+str(index), pair='AAA/USDT',
            features=features, feature_observed_at=clock.now, input_state='closed_only',
            probability=probability, threshold=.5, predicted_at=clock.now,
            feature_input_contract=protocol['feature_input_contract'])
        rows = ledger.rows()
        for role, worker in workers.items():
            selected_rows = rows
            if role == 'baseline_control':
                selected_rows = [{**row, 'original_candidate_would_enter': row['would_enter'],
                    'would_enter': row['baseline_would_enter']} for row in rows]
            worker.market = lambda pair: market(clock, pair, step='.00000001')
            worker.tick(selected_rows, window_start=start, window_end=end)
        clock.advance()
        for worker in workers.values():
            worker.tick([], window_start=start, window_end=end)
        clock.advance()
        for worker in workers.values():
            worker.market = lambda pair, price=exit_price: market(clock, pair, price=price, step='.00000001')
            worker.tick([], window_start=start, window_end=end)
        clock.advance()
        for worker in workers.values():
            worker.tick([], window_start=start, window_end=end)
    clock.now = end
    for worker in workers.values():
        worker.wallet.mark({'AAA/USDT': market(clock, price='110', step='.00000001')[0]},
            {'AAA/USDT': market(clock, price='110', step='.00000001')[1]})
    roles = {}
    for role in workers:
        wallet_path, worker_path = study.paper_role_paths(role)
        roles[role] = export_results(wallet_path, worker_path, as_of=end)
        roles[role]['evaluation_role'] = role
    write(study.paper_results, dict(as_of=end.isoformat(), schema_version='paper-role-export-v1',
        roles=roles, simulated=True, performance_publication_hidden=False,
        real_training_examples_allowed=False, live_promotion_allowed=False))
    evaluated = evaluate_paper(roles['candidate'], roles['baseline_control'], roles['stress_candidate'],
        acceptance, window_start=start, window_end=end, as_of=end, preregistered=True)
    evaluated['protocol_version'] = protocol['protocol_version']
    write(study.paper_acceptance, evaluated)
    return dict(path=path, protocol=protocol, state=state, study=study, sha=model_sha, end=end,
        artifact_path=artifact_path, evaluated=evaluated)


def audit(data, **kwargs):
    return audit_strategy_evidence(data['path'], expected_artifact_sha256=data['sha'],
        state_root=data['state'], clock=lambda: data['end'], **kwargs)


def tree_bytes(path):
    return {str(file.relative_to(path)): file.read_bytes() for file in path.rglob('*') if file.is_file()}


def refresh_reports(data):
    study, end = data['study'], data['end']
    roles = {}
    for role in ('candidate', 'baseline_control', 'stress_candidate'):
        roles[role] = export_results(*study.paper_role_paths(role), as_of=end)
        roles[role]['evaluation_role'] = role
    write(study.paper_results, dict(as_of=end.isoformat(), schema_version='paper-role-export-v1',
        roles=roles, simulated=True, performance_publication_hidden=False,
        real_training_examples_allowed=False, live_promotion_allowed=False))
    policy = json.loads(study.acceptance_policy.read_bytes())
    start = time(data['protocol']['windows']['paper']['start'])+timedelta(seconds=data['protocol']['embargo_seconds'])
    result = evaluate_paper(roles['candidate'], roles['baseline_control'], roles['stress_candidate'],
        policy, window_start=start, window_end=end, as_of=end, preregistered=True)
    result['protocol_version'] = data['protocol']['protocol_version']
    write(study.paper_acceptance, result)
    return roles


def test_sealed_reads_only_protocol_and_collection_registry(tmp_path, monkeypatch):
    path, protocol, state, study = collection(tmp_path)
    end = time(protocol['windows']['paper']['end_exclusive'])
    study.root.mkdir(parents=True)
    study.paper_results.write_bytes(b'forbidden premature rewards')
    original_read = EvidenceFiles.read
    def guarded(self, file, **kwargs):
        if Path(file).resolve() not in {path, path.with_suffix('.sha256'), state/'cash-study-registry.sqlite'}:
            pytest.fail('sealed audit read candidate or rewards')
        return original_read(self, file, **kwargs)
    monkeypatch.setattr(EvidenceFiles, 'read', guarded)
    before = tree_bytes(tmp_path)
    result = audit_strategy_evidence(path, expected_artifact_sha256='a'*64, state_root=state,
        clock=lambda: end-timedelta(seconds=1))
    assert result['status'] == 'sealed_until_paper_end' and result['performance_hidden']
    assert not result['live_admission_granted'] and not result['paper_evidence_pass']
    assert tree_bytes(tmp_path) == before


def test_completed_original_databases_are_recomputed_read_only_and_never_grant_live(tmp_path):
    data = complete(tmp_path)
    before = tree_bytes(tmp_path)
    result = audit(data)
    assert result['status'] == 'research_evidence_recomputed'
    assert result['original_opportunities_verified']
    assert result['evaluation'] == data['evaluated']
    assert set(result['recomputed_role_sha256']) == {'candidate', 'baseline_control', 'stress_candidate'}
    assert len([row for row in result['input_files'] if row['path'].endswith('.sqlite')]) == 9
    assert not result['live_admission_granted'] and not result['live_profitability_established']
    assert tree_bytes(tmp_path) == before


def test_completed_synthetic_positive_pass_still_retains_false_live(tmp_path):
    data = complete(tmp_path)
    result = audit(data)
    assert result['conditional_evaluation_pass'], result['evaluation']['failures']
    # Native marks retain values, but no historical mark quotes. A conditional
    # economic pass cannot certify the unrecorded liquidation-price inputs.
    assert not result['historical_liquidation_values_verified']
    assert not result['paper_evidence_pass']
    assert 'historical_equity_valuation_source_qualification' in result['remaining_live_gates']
    assert not result['live_admission_granted']
    assert not result['evaluation']['live_promotion_allowed']


@pytest.mark.parametrize('change', ['flat_equity', 'cash', 'clock', 'dust_basis'])
def test_mutated_capital_marks_cannot_borrow_recomputed_summaries(tmp_path, change):
    data = complete(tmp_path)
    wallet, _ = data['study'].paper_role_paths('candidate')
    db = sqlite3.connect(wallet)
    if change == 'flat_equity':
        identity, raw = db.execute('SELECT id,payload FROM marks ORDER BY id LIMIT 1').fetchone()
    else:
        identity, raw = db.execute('SELECT id,payload FROM marks ORDER BY id DESC LIMIT 1').fetchone()
    value = json.loads(raw)
    if change == 'flat_equity':
        value['equity'] = value['gross_bid_equity'] = str(Decimal(value['cash'])+3)
    elif change == 'cash':
        for key in ('cash', 'equity', 'gross_bid_equity'):
            value[key] = str(Decimal(value[key])+3)
    elif change == 'clock':
        value['observed_at'] = (time(value['observed_at'])-timedelta(seconds=1)).isoformat()
    else:
        # The first post-Buy mark owns material inventory, which cannot be
        # relabeled as dust even if equity is consistently set to cash.
        for candidate, payload in db.execute('SELECT id,payload FROM marks ORDER BY id'):
            row = json.loads(payload)
            if row['equity'] is not None and Decimal(row['equity']) > Decimal(row['cash'])+1:
                identity, value = candidate, row
                break
        value['nontradable_small_basis_pairs'] = ['AAA/USDT']
        value['equity'] = value['cash']
    with db:
        db.execute('UPDATE marks SET payload=? WHERE id=?', (json.dumps(value), identity))
    db.close()
    refresh_reports(data)
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError, match='mark|equity|dust'):
        audit(data)
    assert tree_bytes(tmp_path) == before


def test_mark_replay_preserves_original_before_and_after_fill_at_same_clock(tmp_path):
    data = complete(tmp_path)
    result = audit(data)
    for role in ('candidate', 'baseline_control', 'stress_candidate'):
        marks = result['mark_cash_audits'][role]
        assert marks['cash_replay_verified'] and marks['marks_checked'] > 0
        assert marks['unreplayed_liquidation_marks'] > 0


@pytest.mark.parametrize('field', ['artifact', 'manifest', 'execution', 'acceptance', 'role', 'report'])
def test_changed_original_inputs_or_retained_summaries_cannot_pass(tmp_path, field):
    data = complete(tmp_path)
    study = data['study']
    if field == 'artifact':
        value = json.loads(data['artifact_path'].read_bytes()); value['bias'] = 2
        write(data['artifact_path'], value)
    elif field == 'manifest':
        value = json.loads(study.candidate.read_bytes()); value['threshold'] = '.6'
        write(study.candidate, value)
    elif field == 'execution':
        value = json.loads(study.execution_policy.read_bytes()); value['wallet']['stake'] = '7'
        write(study.execution_policy, value)
    elif field == 'acceptance':
        value = json.loads(study.acceptance_policy.read_bytes()); value['minimum_buys'] = 3
        write(study.acceptance_policy, value)
    elif field == 'role':
        value = json.loads(study.paper_results.read_bytes()); value['roles']['candidate']['cash'] = '999'
        write(study.paper_results, value)
    else:
        value = json.loads(study.paper_acceptance.read_bytes()); value['candidate']['net_return'] = '999'
        write(study.paper_acceptance, value)
    before = tree_bytes(tmp_path)
    with pytest.raises(ValueError): audit(data)
    assert tree_bytes(tmp_path) == before


def test_another_reviewed_model_pin_cannot_borrow_good_paper(tmp_path):
    data = complete(tmp_path)
    with pytest.raises(ValueError, match='model pin'):
        audit_strategy_evidence(data['path'], expected_artifact_sha256='0'*64,
            state_root=data['state'], clock=lambda: data['end'])


@pytest.mark.parametrize('target', ['protocol', 'policy', 'report', 'stored_payload'])
def test_duplicate_json_fields_are_rejected_even_when_kernel_would_keep_last(tmp_path, target):
    data = complete(tmp_path)
    study = data['study']
    if target == 'stored_payload':
        db = sqlite3.connect(study.predictions)
        with db:
            key, raw = db.execute('SELECT opportunity,payload FROM predictions LIMIT 1').fetchone()
            db.execute('UPDATE predictions SET payload=? WHERE opportunity=?',
                ('{"probability":0,'+raw[1:], key))
        db.close()
    else:
        path = {'protocol': data['path'], 'policy': study.execution_policy,
            'report': study.paper_acceptance}[target]
        value = json.loads(path.read_bytes()); key = next(iter(value))
        path.write_bytes(('{' + json.dumps(key) + ':null,' + path.read_text()[1:]).encode())
        if target == 'protocol':
            path.with_suffix('.sha256').write_text(digest(path.read_bytes()))
    with pytest.raises(ValueError): audit(data)


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_database_sidecars_cannot_be_ignored_in_source_hashes(tmp_path, suffix):
    data = complete(tmp_path)
    wallet, _ = data['study'].paper_role_paths('candidate')
    Path(str(wallet)+suffix).write_bytes(b'unmerged source state')
    with pytest.raises(ValueError, match='sidecars'): audit(data)


def test_missing_source_database_does_not_initialize_replacement(tmp_path):
    data = complete(tmp_path)
    wallet, _ = data['study'].paper_role_paths('candidate')
    wallet.unlink()
    with pytest.raises(FileNotFoundError): audit(data)
    assert not wallet.exists()


def test_future_export_clock_is_rejected(tmp_path):
    data = complete(tmp_path)
    value = json.loads(data['study'].paper_results.read_bytes())
    value['as_of'] = (data['end']+timedelta(seconds=1)).isoformat()
    write(data['study'].paper_results, value)
    with pytest.raises(ValueError, match='finished research'): audit(data)


def test_original_prediction_change_cannot_hide_behind_unchanged_role_reports(tmp_path):
    data = complete(tmp_path)
    db = sqlite3.connect(data['study'].predictions)
    with db:
        key, raw = db.execute('SELECT opportunity,payload FROM predictions LIMIT 1').fetchone()
        value = json.loads(raw); value['probability'] = .9
        db.execute('UPDATE predictions SET payload=? WHERE opportunity=?', (json.dumps(value), key))
    db.close()
    with pytest.raises(ValueError, match='prediction differs'): audit(data)


def test_original_collection_registration_is_required(tmp_path):
    path, protocol, state, study = collection(tmp_path)
    (state/'cash-study-registry.sqlite').unlink()
    with pytest.raises(FileNotFoundError):
        audit_strategy_evidence(path, expected_artifact_sha256='a'*64, state_root=state,
            clock=lambda: time(protocol['frozen_at']))
    assert not (state/'cash-study-registry.sqlite').exists()


def test_source_file_mutation_during_recomputation_rejects_partial_audit(tmp_path, monkeypatch):
    import cryptoforge.strategy_evidence as module
    data = complete(tmp_path)
    original = module.export_results
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        data['artifact_path'].write_bytes(data['artifact_path'].read_bytes()+b' ')
        return result
    monkeypatch.setattr(module, 'export_results', mutate)
    with pytest.raises(ValueError, match='changed during audit'): audit(data)


def test_accepted_losing_opportunity_cannot_be_omitted_with_candidate_rejected_status(tmp_path):
    data = complete(tmp_path)
    study = data['study']
    db = sqlite3.connect(study.predictions)
    raw = db.execute("SELECT payload FROM predictions WHERE opportunity='op1'").fetchone()[0]
    value = json.loads(raw)
    value.update(features=[1.]+[0.]*6, probability=predict_probability([1.]+[0.]*6,
        [1.]+[0.]*6, 0., [0.]*7, [1.]*7), would_enter=True)
    with db:
        db.execute("UPDATE predictions SET payload=? WHERE opportunity='op1'", (json.dumps(value),))
    db.close()
    # Make the retained baseline source consistent with the original ledger;
    # the candidate/stress still silently omit this now accepted losing Buy.
    original = next(row for row in ShadowLedger(study.predictions).rows() if row['opportunity']=='op1')
    _, worker_path = study.paper_role_paths('baseline_control')
    db = sqlite3.connect(worker_path)
    for identity, raw in db.execute('SELECT id,payload FROM intent_links').fetchall():
        link = json.loads(raw)
        if (link.get('source_prediction') or {}).get('opportunity') == 'op1':
            link['source_prediction'] = {**original, 'original_candidate_would_enter': True, 'would_enter': True}
            with db:
                db.execute('UPDATE intent_links SET payload=? WHERE id=?', (json.dumps(link), identity))
    db.close()
    refresh_reports(data)
    assert json.loads(study.paper_acceptance.read_bytes())['paper_evidence_pass']
    with pytest.raises(ValueError, match='omitted accepted'): audit(data)


@pytest.mark.parametrize('change', ['unlinked_queued', 'duplicate_source', 'entry_before_prediction', 'filtered_acquisition'])
def test_source_decisions_intents_and_campaigns_must_correspond(tmp_path, change):
    from cryptoforge.strategy_evidence import verify_opportunities
    data = complete(tmp_path)
    study = data['study']
    roles = json.loads(study.paper_results.read_bytes())['roles']
    candidate = roles['candidate']
    if change == 'unlinked_queued':
        candidate['intents'] = [row for row in candidate['intents'] if row['side'] != 'Buy']
    elif change == 'duplicate_source':
        candidate['campaigns'].append(deepcopy(candidate['campaigns'][0]))
    elif change == 'entry_before_prediction':
        candidate['campaigns'][0]['entry_at'] = time(data['protocol']['windows']['paper']['start']).isoformat()
    else:
        prediction = next(row for row in ShadowLedger(study.predictions).rows() if row['opportunity']=='op1')
        candidate['campaigns'][0]['source_prediction'] = prediction
    manifest = json.loads(study.candidate.read_bytes())
    artifact = json.loads(data['artifact_path'].read_bytes())
    start = time(data['protocol']['windows']['paper']['start'])+timedelta(seconds=data['protocol']['embargo_seconds'])
    with pytest.raises(ValueError):
        verify_opportunities(study, roles, manifest, artifact, data['protocol'], start=start, end=data['end'])


def test_regular_file_check_rejects_fifo_and_directory_without_open(tmp_path):
    import os
    fifo = tmp_path/'pipe'
    os.mkfifo(fifo)
    for path in (fifo, tmp_path):
        with pytest.raises(ValueError, match='regular'):
            EvidenceFiles().read(path)


def test_source_symlink_is_rejected_and_parent_retarget_is_detected(tmp_path):
    source = tmp_path/'source.json'
    source.write_bytes(b'{}')
    link = tmp_path/'link.json'
    link.symlink_to(source)
    with pytest.raises(ValueError, match='non-symlink'):
        EvidenceFiles().read(link)
    first, second = tmp_path/'first', tmp_path/'second'
    first.mkdir(); second.mkdir()
    (first/'source.json').write_bytes(b'{}'); (second/'source.json').write_bytes(b'{}')
    directory = tmp_path/'alias'
    directory.symlink_to(first, target_is_directory=True)
    files = EvidenceFiles(); files.read(directory/'source.json')
    directory.unlink(); directory.symlink_to(second, target_is_directory=True)
    with pytest.raises(ValueError, match='retargeted'): files.verify()


def test_sealed_cli_output_cannot_create_a_directory_on_future_evidence_path(tmp_path, monkeypatch, capsys):
    import scripts.audit_strategy_evidence as cli
    path, protocol, state, study = collection(tmp_path)
    end = time(protocol['windows']['paper']['end_exclusive'])
    original_audit = audit_strategy_evidence
    monkeypatch.setattr(cli, 'audit_strategy_evidence', lambda *args, **kwargs: original_audit(
        path, expected_artifact_sha256='a'*64, state_root=state, clock=lambda: end-timedelta(seconds=1)))
    before = tree_bytes(tmp_path)
    args = ['--protocol', str(path), '--expected-artifact-sha256', 'a'*64, '--state-root', str(state)]
    wallet, _ = study.paper_role_paths('candidate')
    for target in (wallet/'audit.json', study.paper_results/'audit.json', study.candidate):
        assert cli.main(args+['--output', str(target)]) == 1
    dangling = tmp_path/'dangling'
    dangling.symlink_to(tmp_path/'not-created')
    assert cli.main(args+['--output', str(dangling)]) == 1
    dangling.unlink()
    assert tree_bytes(tmp_path) == before
    assert not wallet.exists() and not study.paper_results.exists()
    capsys.readouterr()


def test_cli_has_no_as_of_and_optional_output_cannot_overwrite_sources(tmp_path, monkeypatch, capsys):
    import scripts.audit_strategy_evidence as cli
    data = complete(tmp_path)
    monkeypatch.setattr(cli, 'audit_strategy_evidence', lambda *args, **kwargs: audit(data))
    args = ['--protocol', str(data['path']), '--expected-artifact-sha256', data['sha'],
        '--state-root', str(data['state'])]
    before = tree_bytes(tmp_path)
    assert cli.main(args+['--output', str(data['study'].paper_results)]) == 1
    assert tree_bytes(tmp_path) == before
    output = tmp_path/'audit.json'
    assert cli.main(args+['--output', str(output)]) == 0
    assert json.loads(output.read_bytes())['live_admission_granted'] is False
    assert output.stat().st_mode & 0o777 == 0o600
    assert cli.main(args+['--output', str(output)]) == 1
    with pytest.raises(SystemExit): cli.main(args+['--as-of', data['end'].isoformat()])
    capsys.readouterr()
