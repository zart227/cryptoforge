from dataclasses import replace
from decimal import Decimal
import pytest
from cryptoforge.strategy_extension_study import freeze_study,evaluate_candidate,signal_sets
from cryptoforge.research_attempts import ResearchAttempts,identity
from test_trade_simulator import history
import json
from pathlib import Path


def fixture(tmp_path):
    ledger=ResearchAttempts(tmp_path/'ledger.sqlite')
    receipt=freeze_study(tmp_path,ledger)
    return receipt,ledger


def test_declared_four_arm_grid_is_budgeted_before_outcomes(tmp_path):
    receipt,ledger=fixture(tmp_path);manifest=receipt['manifest']
    assert identity(manifest)==receipt['study_sha256'] and len(manifest['grid'])==4
    assert ledger.budget_usage(manifest['budget_protocol_id'])=={'support_bounce':2,'compression_breakout':2}
    for candidate in manifest['grid']:assert ledger.result(receipt['study_sha256'],candidate) is None


def test_memory_profile_preserves_original_search_budget_identity(tmp_path):
    original=json.loads(Path('config/research-protocol-v1.json').read_bytes())
    profile=json.loads(json.dumps(original));profile['resources']['min_available_memory_mb']=1024
    profile['resource_override']={'new_minimum_mib':1024}
    path=tmp_path/'resources.json';path.write_text(json.dumps(profile))
    ledger=ResearchAttempts(tmp_path/'ledger.sqlite')
    receipt=freeze_study(tmp_path,ledger,path)
    assert receipt['manifest']['budget_protocol_id']==__import__('hashlib').sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
    assert receipt['manifest']['resource_protocol_path']==str(path.resolve())


def test_resource_profile_cannot_change_trade_stake(tmp_path):
    profile=json.loads(Path('config/research-protocol-v1.json').read_bytes())
    profile['resources']['min_available_memory_mb']=1024;profile['portfolio']['stake']='7'
    path=tmp_path/'resources.json';path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='only authorized memory reserve'):
        freeze_study(tmp_path,ResearchAttempts(tmp_path/'ledger.sqlite'),path)


def test_cash_only_is_zero_and_no_activity_does_not_establish_profitability(tmp_path):
    receipt,_=fixture(tmp_path);m=receipt['manifest'];data={'ETH/USDT':history(count=300)}
    for candidate in m['grid']:
        result=evaluate_candidate(data,m,candidate)
        assert result['roles']['filtered']['no_entry_sample']
        assert result['roles']['filtered']['net_pnl']=='0'
        assert not result['live_promotion_allowed'] and not result['filter_subset_of_baseline_verified']


def test_extension_opportunity_can_trade_without_becoming_a_model_filter(tmp_path):
    receipt,_=fixture(tmp_path);m=receipt['manifest'];rows=history(count=300)
    rows[119]=replace(rows[119],close=Decimal('100.5'),volume=Decimal(4000))
    data={'ETH/USDT':rows};candidate={'family':'support_bounce','risk':'atr'}
    _,selected=signal_sets(data,m,'support_bounce')
    assert rows[119].open_time in selected['ETH/USDT']
    result=evaluate_candidate(data,m,candidate)
    assert result['roles']['filtered']['executed_trades']>=1
    assert result['roles']['filtered']['recorded_entry_risk_plans']==len(selected['ETH/USDT'])
    assert result['baseline_risk_method']=='atr'
    assert not result['model_fitting_performed']
    with pytest.raises(ValueError,match='declared'):evaluate_candidate(data,m,{'family':'other','risk':'atr'})
