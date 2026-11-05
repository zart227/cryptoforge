from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import pytest
from cryptoforge import research_readiness as m

NOW='2026-10-26T09:00:00+00:00'

@pytest.fixture
def facts():
    return {'state':{'numeric_lifetime_used':3,'numeric_lifetime_cap':3,'approved_executable_continuation_protocol':False,
        'main_runtime_integrated':False,'early_primary_captured_label_horizons':0,'installed_local_semantic_backend_qualified':False},
        'observed_at':{k:'2026-10-26T08:00:00+00:00'for k in ('source','free_catalog','provider_limits')},
        'missing_original_operational_bindings':4,'fixed_free_catalog_entry_verified':True,'shared_provider_free_daily_remaining':50}

def test_full_provider_quota_never_overrides_exhausted_project_budget_and_missing_protocol(facts):
    r=m.assess(facts,NOW,'generative')
    assert r['status']=='blocked' and r['prototype_numeric_attempts_remaining']==0
    assert len(r['blocking_reasons'])==8 and r['shared_provider_free_daily_remaining']==50
    assert not r['operational_actions_enabled'] and not r['shared_provider_counter_is_project_allowance']
    assert not r['manual_patch_required_as_new_MVP_gate']

def test_semantic_backend_is_required_only_for_semantic_branch(facts):
    a=m.assess(facts,NOW,'generative');b=m.assess(facts,NOW,'semantic')
    assert 'installed_semantic_backend_unqualified'not in a['blocking_reasons']
    assert b['blocking_reasons']==a['blocking_reasons']+['installed_semantic_backend_unqualified']

@pytest.mark.parametrize('seconds,blocked',[(-1,True),(0,False),(900,False),(901,True)])
def test_evidence_freshness_boundary_and_future_observation(facts,seconds,blocked):
    facts['observed_at']['source']=(datetime.fromisoformat(NOW)-timedelta(seconds=seconds)).isoformat()
    r=m.assess(facts,NOW,'generative')
    assert any(reason.startswith('source_')for reason in r['blocking_reasons'])is blocked

@pytest.mark.parametrize('field,value',[('numeric_lifetime_used',True),('numeric_lifetime_cap',-1),('approved_executable_continuation_protocol',1)])
def test_nonboolean_prerequisite_or_noninteger_budget_refused(facts,field,value):
    facts['state'][field]=value
    with pytest.raises(ValueError):m.assess(facts,NOW,'generative')

def test_fresh_complete_synthetic_evidence_still_cannot_authorize_operations(facts):
    facts['state'].update(numeric_lifetime_used=0,approved_executable_continuation_protocol=True,main_runtime_integrated=True,early_primary_captured_label_horizons=1)
    facts['observed_at']={k:NOW for k in facts['observed_at']};facts['missing_original_operational_bindings']=0
    r=m.assess(facts,NOW,'generative')
    assert r['status']=='evidence_checks_passed_review_only' and not r['operational_actions_enabled']
    assert not r['existing_phase_or_trainer_admission_replaced']

def test_unknown_provider_quota_stays_null_and_missing_clock_refused(facts):
    facts['shared_provider_free_daily_remaining']=None
    assert m.assess(facts,NOW,'generative')['shared_provider_free_daily_remaining']is None
    del facts['observed_at']['source']
    with pytest.raises(ValueError):m.assess(facts,NOW,'generative')

def test_safe_cli_policy_and_invalid_timestamp_errors(facts,tmp_path,capsys,monkeypatch):
    root=Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-readiness-v1.json').read_text())==m.POLICY
    assert m.main(['verify','--directory',str(tmp_path/'secret')])==2
    assert 'secret'not in capsys.readouterr().out
    facts['observed_at']['source']='SECRET'
    with pytest.raises(ValueError)as e:m.assess(facts,NOW,'generative')
    assert 'SECRET'not in str(e.value)
    monkeypatch.setitem(m.POLICY,'operational_actions_enabled',True)
    with pytest.raises(ValueError):m._guard()
