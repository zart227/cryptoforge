from copy import deepcopy
from pathlib import Path
import sqlite3
import pytest
from cryptoforge.research_attempts import ResearchAttempts


def manifest(value=1,dataset='a'):
    return {'dataset':dataset,'grid':[{'family':'trend','value':value}]}


def test_repeat_restores_immutable_result_and_different_data_is_a_new_attempt(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite');m=manifest();c=m['grid'][0]
    study=ledger.register(m,protocol_id='p',maximum_per_family=1)
    assert ledger.result(study,c) is None
    result={'net_pnl':'-1'};ledger.record(study,c,result)
    assert ledger.register(m,protocol_id='p',maximum_per_family=1)==study
    assert ledger.result(study,c)==result
    with pytest.raises(ValueError,match='immutable'):ledger.record(study,c,{'net_pnl':'1'})
    other=ledger.register(manifest(dataset='b'),protocol_id='p',maximum_per_family=1)
    assert other!=study and ledger.result(other,c) is None


def test_budget_cannot_expand_and_failed_registration_rolls_back(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite');ledger.register(manifest(),protocol_id='p',maximum_per_family=1)
    with pytest.raises(ValueError,match='budget exhausted'):ledger.register(manifest(2),protocol_id='p',maximum_per_family=1)
    with pytest.raises(ValueError,match='cannot change'):ledger.register(manifest(2),protocol_id='p',maximum_per_family=2)
    assert ledger.register(manifest(2),protocol_id='new-p',maximum_per_family=1)


def test_failed_attempt_is_retained_and_foreign_database_refused(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite');m=manifest();c=m['grid'][0]
    study=ledger.register(m,protocol_id='p',maximum_per_family=1);ledger.record(study,c,{'error':'invalid_data'},failed=True)
    with pytest.raises(ValueError,match='failed attempt'):ledger.result(study,c)
    foreign=tmp_path/'real.sqlite';db=sqlite3.connect(foreign);db.execute('CREATE TABLE trades (id TEXT)');db.close()
    with pytest.raises(ValueError,match='isolated'):ResearchAttempts(foreign).register(m,protocol_id='p',maximum_per_family=1)


def test_changing_protocol_checksum_cannot_reset_same_version_budget(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite')
    ledger.register(manifest(),protocol_id='original-sha',protocol_version='v1',maximum_per_family=1)
    with pytest.raises(ValueError,match='without a new version'):
        ledger.register(manifest(2),protocol_id='changed-sha',protocol_version='v1',maximum_per_family=100)
    assert ledger.register(manifest(2),protocol_id='changed-sha',protocol_version='v2',maximum_per_family=1)


def test_execution_changes_consume_budget_but_data_only_changes_do_not(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite');m=manifest();m['base_config']={'entry_fee':'.001'}
    ledger.register(m,protocol_id='p',maximum_per_family=1)
    different_data=deepcopy(m);different_data['dataset']='new'
    ledger.register(different_data,protocol_id='p',maximum_per_family=1)
    assert ledger.budget_usage('p')=={'trend':1}
    expensive=deepcopy(m);expensive['base_config']['entry_fee']='.002'
    with pytest.raises(ValueError,match='budget exhausted'):ledger.register(expensive,protocol_id='p',maximum_per_family=1)
    assert ledger.budget_usage('p')=={'trend':1}


def test_new_implementation_cannot_reuse_legacy_budget_identity(tmp_path):
    ledger=ResearchAttempts(tmp_path/'research.sqlite');m=manifest()
    ledger.register(m,protocol_id='p',maximum_per_family=2)
    new=deepcopy(m);new['implementation_hashes']={'strategy':'sha1','simulator':'sha2'}
    ledger.register(new,protocol_id='p',maximum_per_family=2)
    assert ledger.budget_usage('p')=={'trend':2}
