"""Historical charges are hypothetical, bounded by original caps and never applied."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from cryptoforge import research_historical_debits as m
from test_research_budget_inventory import inventory_request, ref
from test_research_phase import migrated
from test_research_run_budget import bindings


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    folder = tmp_path_factory.mktemp('historical-debits')
    original = inventory_request.__wrapped__(folder)
    common_folder = folder/'common'; common_folder.mkdir()
    budget, _, _ = migrated(common_folder)
    options = {'bindings': {key: str(path) for key, path in bindings(common_folder).items()},
        'semantic_live_ledger': str(common_folder/'live.sqlite')}
    original['journals'].append(ref(budget.path, 'common_v5', 'common', options))
    pack = folder/'inventory'; m.inventory.prepare(pack, original)
    return pack, m.bind(pack)


def test_hand_computed_visible_reservation_charges_preserve_native_snapshot(base):
    _, bound = base; report = m.compose(*bound)
    assert report['original_native_common']['total_reserved_actions'] == 2
    assert report['hypothetical_after_charges']['total_reserved_actions'] == 5
    assert report['hypothetical_after_charges']['reserved_by_kind']['fit'] == 3
    assert report['hypothetical_after_charges']['reserved_by_kind']['proposal'] == 1
    assert report['hypothetical_after_charges']['reserved_allocations'] == {'input_tokens':32000,'output_tokens':2048,'wall_ms':145000}
    assert report['unchanged_limits']['by_kind']['fit'] == 12
    assert report['overlap_groups_preserved'] == 1
    assert 'execution_replay_copy_lineage_unresolved' in report['activation_blockers']
    assert 'operational_inner_journals_not_qualified' in report['activation_blockers']
    assert report['actual_total_consumption'] is None and report['account_wide_spend_usd'] is None
    assert report['alternative_additional_actions_by_kind']['numeric_control'] == 0
    for name in ('journal_or_caps_or_reservations_changed', 'new_allowances_or_refunds', 'native_budget_admission_rights_granted',
                 'fit_executed', 'provider_called', 'model_prediction_performed', 'production_promotion_authorized'):
        assert report[name] is False


@pytest.mark.parametrize('tokens,expected', [
    ({'input_tokens':None,'output_tokens':None,'total_tokens':None}, {'input_tokens':32000,'output_tokens':2048}),
    ({'input_tokens':50000,'output_tokens':100,'total_tokens':50100}, {'input_tokens':50000,'output_tokens':2048}),
    ({'input_tokens':None,'output_tokens':100,'total_tokens':60000}, {'input_tokens':59900,'output_tokens':2048}),
    ({'input_tokens':0,'output_tokens':0,'total_tokens':0}, {'input_tokens':32000,'output_tokens':2048}),
])
def test_full_reservations_and_known_overruns_do_not_refund(tokens, expected):
    assert m._charge_tokens(tokens, {'input_tokens':32000,'output_tokens':2048}) == expected


def test_invalid_usage_not_normalized_to_zero():
    with pytest.raises(ValueError): m._charge_tokens({'input_tokens':10,'output_tokens':20,'total_tokens':1}, {'input_tokens':32000,'output_tokens':2048})


def test_kind_limit_can_exhaust_without_mutating_native_remaining(base):
    _, bound = base; binding, source, policies = deepcopy(bound)
    legacy = next(entry for entry in source['journals'] if entry['kind'] == 'attempts')
    # A synthetic allocation matrix, not an original-journal update or invocation.
    original = legacy['records'][0]
    for index in range(9): legacy['records'].append({**original,'study':m.digest({'synthetic_extra':index})})
    legacy['reserved_attempts'] += 9
    source['inventory_sha256'] = m.digest({key:value for key,value in source.items() if key!='inventory_sha256'})
    binding['inventory_sha256'] = source['inventory_sha256']
    report = m.compose(binding, source, policies)
    assert report['original_native_common']['reserved_by_kind']['fit'] == 1
    assert report['hypothetical_after_charges']['reserved_by_kind']['fit'] == 12
    assert report['alternative_additional_actions_by_kind']['fit'] == 0
    assert 'dry_scenario_fit_reservation_limit_exhausted' in report['activation_blockers']


def test_alternative_action_counts_share_one_resource_balance(base):
    report = m.compose(*base[1])
    assert report['scenarios_share_one_budget_and_cannot_be_added'] is True
    assert report['alternative_semantic_action_assumption_questions_per_action'] == 1
    assert report['native_budget_admission_rights_granted'] is False


def test_cannot_charge_an_already_bound_inner_ledger_without_exact_linkage(base):
    binding, source, policies = deepcopy(base[1])
    common = next(entry for entry in source['journals'] if entry['kind'] == 'common_v5')
    source['journals'][0]['path_sha256'] = common['native_snapshot']['manifest']['journal_path_hashes']['proposal']
    source['inventory_sha256'] = m.digest({key:value for key,value in source.items() if key!='inventory_sha256'})
    binding['inventory_sha256'] = source['inventory_sha256']
    with pytest.raises(ValueError,match='already_bound_inner_journal'): m.compose(binding,source,policies)


def test_changed_report_cannot_be_separated_from_external_inventory_binding(base):
    binding, source, policies = deepcopy(base[1])
    source['account_wide_spend_usd'] = 0
    source['inventory_sha256'] = m.digest({key:value for key,value in source.items() if key!='inventory_sha256'})
    with pytest.raises(ValueError,match='verified_original_inventory'):m.compose(binding,source,policies)


def test_private_dry_plan_replay_and_rehashed_activation_forgery(base,tmp_path):
    source,_ = base
    report = m.prepare(tmp_path/'proposal',source)
    assert m.verify(tmp_path/'proposal') == report
    assert (tmp_path/'proposal').stat().st_mode&0o777 == 0o700
    assert all(path.stat().st_mode&0o777==0o600 for path in (tmp_path/'proposal').iterdir())
    with pytest.raises(ValueError,match='new_historical_debits'):m.prepare(tmp_path/'proposal',source)
    report['native_budget_admission_rights_granted']=True
    report['proposal_sha256']=m.digest({key:value for key,value in report.items() if key!='proposal_sha256'})
    (tmp_path/'proposal/proposal.json').write_text(m.canonical(report)+'\n')
    with pytest.raises(ValueError,match='historical_debit_proposal_changed'):m.verify(tmp_path/'proposal')


def test_original_journal_bytes_are_unchanged_after_proposal(base,tmp_path):
    source,_ = base; request=json.loads((source/'request.json').read_text())
    before={entry['path']:Path(entry['path']).read_bytes() for entry in request['journals']}
    m.prepare(tmp_path/'proposal',source);m.verify(tmp_path/'proposal')
    assert all(Path(path).read_bytes()==raw for path,raw in before.items())


def test_policy_has_no_activation_or_apply_command(base,tmp_path,monkeypatch,capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-historical-debits-v1.json').read_text())==m.POLICY
    with pytest.raises(SystemExit) as error:m.main(['apply'])
    assert error.value.code==2
    monkeypatch.setitem(m.POLICY,'activation_enabled',True)
    with pytest.raises(ValueError,match='policy_changed'):m.compose(*base[1])


def test_safe_cli_refusal_does_not_expose_private_path(tmp_path,capsys):
    assert m.main(['verify','--directory',str(tmp_path/'private-secret-path')])==2
    assert 'private-secret-path' not in capsys.readouterr().out
