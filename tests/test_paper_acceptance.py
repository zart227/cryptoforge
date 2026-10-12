from copy import deepcopy
from datetime import UTC,datetime,timedelta
from pathlib import Path
import json
import pytest

from cryptoforge.paper_acceptance import evaluate_paper,AcceptanceRegistry

START=datetime(2026,12,18,tzinfo=UTC);END=START+timedelta(days=14)


def policy():
    p=json.loads(Path('config/paper-acceptance-policy-v1.json').read_bytes());p.update(status='frozen',minimum_buys=14,
        maximum_mark_gap_seconds=86401,maximum_endpoint_gap_seconds=1)
    return p


def result(role='candidate',growth='.001',stress=False):
    config={'stake':'6','max_dust_basis_fraction':'.01','entry_fee':'.0018','exit_fee':'.0018','slippage':'.0005'}
    if stress:config.update(entry_fee='.0036',exit_fee='.0036',slippage='.001')
    campaigns=[{'paper_buy_intent':str(i),'pair':f'COIN{i%4}/USDT','entry_at':(START+timedelta(days=i,hours=1)).isoformat(),
        'has_exit':True,'remaining_basis':'0','cash_recovery_net_dust_zero':'.1','closed_at':(START+timedelta(days=i,hours=2)).isoformat()}
        for i in range(14)]
    from decimal import Decimal
    marks=[{'observed_at':(START+timedelta(days=i)).isoformat(),'equity':str(Decimal(100)*(1+Decimal(growth)*i))} for i in range(15)]
    return {'status':'simulated_evidence_only','capital':'100','candidate_artifact_sha256':'a'*64,
        'policy':{'config':config},'campaigns':campaigns,'equity_marks':marks,'intents':[],'fills':[],
        'worker_quality_errors':[],'seen_predictions':[{'id':str(i),'status':'queued'} for i in range(14)]}


def evaluate(c=None,b=None,s=None,p=None,as_of=END,frozen=True):
    return evaluate_paper(c or result(),b or result('baseline',growth='-.001'),s or result('stress',growth='.0005',stress=True),
        p or policy(),window_start=START,window_end=END,as_of=as_of,preregistered=frozen)


def test_complete_conditional_evidence_pass_does_not_promote_real_model():
    report=evaluate()
    assert report['paper_evidence_pass'] and not report['live_promotion_allowed']
    assert not report['live_profitability_established']


def test_before_end_no_statistics_or_pass_are_available():
    report=evaluate(as_of=END-timedelta(seconds=1))
    assert report['performance_hidden'] and 'candidate' not in report and not report['paper_evidence_pass']


def test_unknown_equity_and_unresolved_position_override_positive_trades():
    c=result();c['equity_marks'][3]['equity']=None
    c['campaigns'][0]['remaining_basis']='6'
    report=evaluate(c=c)
    assert not report['paper_evidence_pass']
    assert 'material_or_unclosed_positions' in report['failures'] and 'incomplete_equity_observation' in report['failures']


def test_unregistered_criteria_cannot_authorize_a_good_result():
    assert 'acceptance_policy_not_observed_before_paper' in evaluate(frozen=False)['failures']


def test_expired_source_opportunities_cannot_hide_failed_paper_orders():
    c=result();c['seen_predictions'][0]['status']='source_prediction_expired'
    assert 'source_opportunities_missing_or_expired' in evaluate(c=c)['failures']


def test_control_and_stress_cannot_use_different_source_opportunities():
    b=result(growth='-.001');b['seen_predictions'].pop()
    s=result(growth='.0005',stress=True);s['seen_predictions'].pop()
    report=evaluate(b=b,s=s)
    assert not report['paper_evidence_pass']
    assert 'baseline_source_opportunities_not_identical' in report['failures']
    assert 'stress_source_opportunities_not_identical' in report['failures']


def test_late_exit_cannot_improve_the_completed_window():
    c=result();c['campaigns'][0]['closed_at']=(END+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='late closing'):evaluate(c=c)


def test_acceptance_criterion_receipt_must_match_observed_immutable_registry(tmp_path):
    p=policy();raw=json.dumps(p).encode();registry=AcceptanceRegistry(tmp_path/'criteria.sqlite',clock=lambda:START-timedelta(days=1))
    receipt=registry.freeze(raw,protocol_sha='b'*64);registry.verify(raw,receipt)
    changed={**receipt,'observed_at':(START-timedelta(days=2)).isoformat()}
    with pytest.raises(ValueError,match='actual observed'):registry.verify(raw,changed)


def test_paired_comparison_rejects_missing_days_and_changed_stress_rules():
    b=result(growth='-.001');b['equity_marks'].pop(4)
    s=result(growth='.0005',stress=True);s['policy']['config']['stake']='10'
    s['seen_predictions'][0]['status']='source_prediction_expired'
    failures=evaluate(b=b,s=s)['failures']
    assert 'no_paired_positive_bootstrap_bound' in failures
    assert 'stress_execution_assumptions_not_equal' in failures
    assert 'stress_source_opportunities_missing_or_expired' in failures


def test_registry_recovery_preserves_original_clock_and_exact_bytes(tmp_path):
    registry=AcceptanceRegistry(tmp_path/'criteria.sqlite',clock=lambda:START-timedelta(days=1))
    assert registry.registered('b'*64) is None
    assert not registry.path.exists()
    raw=json.dumps(policy()).encode();receipt=registry.freeze(raw,protocol_sha='b'*64)
    registry.clock=lambda:END
    restored,original=registry.registered('b'*64)
    assert restored==raw and original==receipt
    assert registry.registered('c'*64) is None


def test_freeze_command_recovers_missing_files_but_refuses_parameter_changes(tmp_path,monkeypatch):
    import hashlib,shutil
    from scripts.freeze_paper_acceptance import main
    config=tmp_path/'config';config.mkdir()
    for name in ('live-cash-recovery-protocol-v1.json','live-cash-recovery-protocol-v1.sha256','paper-acceptance-policy-v1.json'):
        shutil.copy(Path('config')/name,config/name)
    path=config/'paper-acceptance-policy-v1.json';raw=path.read_bytes()
    registry=AcceptanceRegistry(tmp_path/'.local/state/paper-acceptance-registry.sqlite',clock=lambda:datetime(2026,10,8,tzinfo=UTC))
    receipt=registry.freeze(raw,protocol_sha=hashlib.sha256((config/'live-cash-recovery-protocol-v1.json').read_bytes()).hexdigest())
    path.unlink();monkeypatch.chdir(tmp_path)
    main([])
    assert path.read_bytes()==raw
    assert json.loads(path.with_suffix('.freeze.json').read_bytes())==receipt
    changed=json.loads(raw);changed['minimum_buys']+=1;path.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='cannot change'):main([])


@pytest.mark.parametrize('role,gate',[('candidate','worker_errors_or_pending_intents'),('baseline','baseline_quality_errors'),('stress','stress_quality_errors')])
@pytest.mark.parametrize('reason',['expired_signal','source_prediction_expired'])
def test_queued_signal_expiry_cannot_disappear_from_completeness_gate(role,gate,reason):
    c=result();b=result(growth='-.001');s=result(growth='.0005',stress=True)
    {'candidate':c,'baseline':b,'stress':s}[role]['intents']=[{'status':'rejected','reason':reason}]
    assert gate in evaluate(c=c,b=b,s=s)['failures']


def test_normal_portfolio_risk_rejection_is_accounted_without_data_failure():
    c=result();c['intents']=[{'status':'rejected','reason':'insufficient_cash'}]
    assert evaluate(c=c)['paper_evidence_pass']
    c['worker_quality_error_count']=1
    assert 'worker_errors_or_pending_intents' in evaluate(c=c)['failures']
