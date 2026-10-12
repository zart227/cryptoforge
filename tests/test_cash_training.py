from copy import deepcopy
from datetime import timedelta
import pytest
from cryptoforge.cash_training import fit_cash_candidate
from test_live_learning_protocol import protocol,ready_rows,START,row


def snapshots():
    rows=ready_rows();rows.pop('sealed_test')
    for split,values in rows.items():
        for r in values:
            r.update(cost='6',cash_recovery_net='.1' if r['example']['label'] else '-.1')
            r['example']['features'][0]=r['example']['label']*.01
    return rows


def fit(rows=None,healthy=True,day=42):
    return fit_cash_candidate(protocol(),rows or snapshots(),as_of=START+timedelta(days=day),source_healthy=healthy)


def test_only_preregistered_trials_and_no_live_or_short_head():
    artifact=fit()
    assert [t['l2'] for t in artifact['validation_search']]==['0.001','0.01','0.1']
    assert len(artifact['weights'])==7 and artifact['selected_l2'] in protocol()['configuration_budget']['l2_values']
    assert artifact['live_eligible'] is False and 'short_weights' not in artifact
    assert artifact['config']['holdout_used'] is False
    assert fit()==artifact


def test_normalization_is_train_only_and_invalid_future_rows_are_excluded():
    before=fit();rows=snapshots()
    for r in rows['validation']:r['example']['features'][0]=1000
    after=fit(rows)
    assert before['means']==after['means'] and before['stds']==after['stds']
    late=row('late',25,known_day=28);late.update(cost='6',cash_recovery_net='-.1')
    rows=snapshots();rows['train'].append(late)
    assert fit(rows)['config']['training_provenance']['train']['count']==2


def test_holdout_deadline_health_and_readiness_fail_before_fitting():
    rows=snapshots();rows['sealed_test']=[{'malformed':'never inspected'}]
    with pytest.raises(ValueError,match='holdout'):fit(rows)
    with pytest.raises(ValueError,match='deadline'):fit(day=43)
    with pytest.raises(ValueError,match='qualified'):fit(healthy=False)
    with pytest.raises(ValueError,match='qualified'):fit(day=40)


def test_label_must_match_actual_cash_outcome():
    rows=snapshots();rows['train'][0]['cash_recovery_net']='.1'
    with pytest.raises(ValueError,match='mismatch'):fit(rows)


def test_registration_requires_original_all_trial_receipt_and_identical_snapshots():
    import hashlib,json
    from cryptoforge.cash_training import verify_fit_provenance
    artifact=fit();raw=json.dumps(artifact).encode()
    report={'artifact_payload':raw.decode(),'artifact_sha256':hashlib.sha256(raw).hexdigest(),
            'trials':artifact['validation_search'],'live_promotion_allowed':False}
    kwargs={'as_of':START+timedelta(days=42),'source_healthy':True}
    verify_fit_provenance(raw,report,protocol(),snapshots(),**kwargs)
    changed=deepcopy(report);changed['trials'].pop()
    with pytest.raises(ValueError,match='original'):verify_fit_provenance(raw,changed,protocol(),snapshots(),**kwargs)
    rows=snapshots();rows['train'][0]['example']['features'][0]=.02
    with pytest.raises(ValueError,match='snapshots'):verify_fit_provenance(raw,report,protocol(),rows,**kwargs)


def test_cli_recovers_original_artifact_without_reading_new_data(tmp_path,monkeypatch):
    import hashlib,json,shutil
    from pathlib import Path
    from scripts.train_cash_candidate import main
    config=tmp_path/'config';config.mkdir()
    for name in ('live-cash-recovery-protocol-v1.json','live-cash-recovery-protocol-v1.sha256','cash-training-fit-policy-v1.json','cash-training-fit-policy-v1.sha256'):
        shutil.copy(Path('config')/name,config/name)
    raw=json.dumps(fit()).encode();sha=hashlib.sha256(raw).hexdigest()
    output=tmp_path/'.local/state/cash-training';output.mkdir(parents=True)
    report={'artifact_payload':raw.decode(),'artifact_sha256':sha,
            'protocol_sha256':hashlib.sha256((config/'live-cash-recovery-protocol-v1.json').read_bytes()).hexdigest()}
    (output/'fit-report.json').write_text(json.dumps(report));monkeypatch.chdir(tmp_path)
    main([]);path=output/(sha+'.json');assert path.read_bytes()==raw
    main([]);assert path.read_bytes()==raw
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):main([])


def test_validation_diagnostics_keep_small_wins_and_large_losses_in_actual_cash():
    from cryptoforge.cash_training import validation_diagnostics
    rows=snapshots()['validation'];rows[0]['cash_recovery_net']='-.5';rows[1]['cash_recovery_net']='.1'
    report=validation_diagnostics(rows,[.9,.9],threshold=.5,train_positive_rate=.5)
    cohorts=report['fixed_threshold_factual_cohorts']
    assert cohorts['accepted']['cash_recovery_net_sum']=='-0.4'
    assert cohorts['rejected']['buy_orders']==0 and cohorts['all']['buy_orders']==2
    assert report['calibration_bins'][-1]['positive_fraction']==.5
    assert not report['selection_uses_these_diagnostics'] and not report['live_profitability_established']


def test_fit_diagnostics_never_use_holdout_or_change_fixed_selection():
    artifact=fit();diagnostics=artifact['validation_diagnostics']
    assert diagnostics['fixed_threshold_factual_cohorts']['all']['buy_orders']==2
    assert sum(b['count'] for b in diagnostics['calibration_bins'])==2
    winner=min(artifact['validation_search'],key=lambda trial:trial['validation_log_loss'])
    assert artifact['selected_l2']==winner['l2']
