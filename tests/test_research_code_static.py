from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from cryptoforge import research_code_static as static, research_code_preview as preview, research_code_budget as code
from cryptoforge import research_run_budget as common
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY
from cryptoforge.training_diagnostics import canonical, digest
from test_research_code_budget import migrated, base
from test_research_code_preview import proposal, BASE


def source(expression):
    return "def candidate_features(window):\n    return {'value': " + expression + "}\n"


def bundle(tmp_path, name='preview', *, candidate=None, wording=None):
    candidate = source('1.0') if candidate is None else candidate
    patch = '--- a/research/feature_candidate.py\n+++ b/research/feature_candidate.py\n@@ -1,2 +1,' + str(len(candidate.splitlines())) + ' @@\n'
    patch += ''.join('-' + line + '\n' for line in BASE.splitlines())
    patch += ''.join('+' + line + '\n' for line in candidate.splitlines())
    item = proposal(BASE, patch)
    if wording: item['hypothesis'] = wording
    directory = tmp_path / name
    preview.stage_preview(directory, item, preview.POLICY)
    return directory


def registered(tmp_path, *, candidate=None, **kwargs):
    budget = migrated(tmp_path, **kwargs); directory = bundle(tmp_path, candidate=candidate)
    code.check_preview(budget, directory)
    return budget, directory


@pytest.mark.parametrize('expression', ['0', '1.0', '-1', '+1.5',
    "window[-1]['close'] / window[-2]['close'] - 1",
    "(window[0]['high'] - window[0]['low']) / window[0]['close']",
    "abs(window[-64]['open'] - window[63]['close'])",
    "max(0, min(1, window[-1]['volume'] / 1000))"])
def test_closed_numeric_window_expressions_pass_without_execution(expression):
    result = static._analyze(source(expression))
    assert result['verdict'] == 'passed_static_contract' and result['syntax_parsed']
    assert not result['candidate_executed'] and not result['bytecode_created']
    assert not result['input_availability_verified'] and not result['numeric_validity_verified']
    assert not result['runtime_contract_verified'] and not result['execution_authorized']


def test_window_reads_are_exact_deduplicated_and_have_a_declared_minimum():
    result = static._analyze(source("window[-3]['close'] + window[4]['volume'] + window[-3]['close']"))
    assert result['window_reads'] == [{'index': -3, 'field': 'close'}, {'index': 4, 'field': 'volume'}]
    assert result['required_window_size'] == 5
    assert static._analyze(source('1'))['required_window_size'] == 0


@pytest.mark.parametrize('candidate', [
    "import os\n" + source('1'), source('1') + 'print("module side effect")\n',
    '@dangerous()\n' + source('1'), source('1').replace('(window)', '(window=dangerous())'),
    source('1').replace('(window)', '(window: dangerous())'),
    source('1').replace('(window)', '(*window)'), source('1').replace('(window)', '(window, extra)'),
    source('1').replace('(window)', '(window, /)'), source('1').replace('(window)', '(window, *, extra=1)'),
    source('1').replace('candidate_features', 'changed'), source('1').replace('def ', 'async def '),
    source('1').replace("    return", '    x = 1\n    return'), source('1').replace("'value'", "'target'"),
    source('1').replace("'value': 1", "'value': 1, 'extra': 2"),
    source('1').replace("{'value': 1}", 'dict(value=1)'),
    source('1').replace("{'value': 1}", "{**window}"), source('1') + source('2'),
    source('1') + '# type: ignore\n',
])
def test_module_signature_body_and_output_are_fixed_independently_of_candidate(candidate):
    result = static._analyze(candidate)
    assert result['verdict'] == 'rejected' and result['issue'] is not None
    assert not result['candidate_executed'] and not result['execution_authorized']


@pytest.mark.parametrize('expression', [
    "__import__('os').system('anything')", "open('/secret').read()", 'eval("1")',
    'window.__class__', "window[-1].get('close')", 'lambda: 1',
    "window[1:]['close']", "window[len(window)-1]['close']", "window[True]['close']",
    "window[64]['close']", "window[-65]['close']", "window[-1]['future_return']",
    "window[-1]['label']", 'future_label', '[1 for x in window]', '(x := 1)',
    '1 if window else 2', '2 ** 1000000', '1 << 100', 'True', "'secret'", '1j',
    'float("nan")', '1e999', '1000001', '9' * 1000, '1 / 0',
    'abs(1, 2)', 'min(1)', 'max(1, 2, 3, 4, 5)', 'min(window)', 'max(1, 2, key=abs)', 'abs(*window)',
])
def test_stateful_unbounded_future_field_and_non_numeric_constructs_are_rejected(expression):
    result = static._analyze(source(expression))
    assert result['verdict'] == 'rejected' and result['issue'] is not None
    assert result['window_reads'] == []


def test_structural_contract_is_not_a_numeric_or_causal_proof():
    result = static._analyze(source("window[0]['close'] / (1 - 1)"))
    assert result['verdict'] == 'passed_static_contract'
    assert not result['numeric_validity_verified'] and not result['input_availability_verified']
    assert not result['independent_dynamic_tests_executed'] and not result['feature_utility_verified']


@pytest.mark.parametrize('candidate,rule', [
    (source('1 +'), 'python_syntax'), (source(' + '.join(['1'] * 80)), 'ast_depth_limit'),
    (source('max(' + ','.join(['1'] * 600) + ')'), 'ast_node_limit'),
    (source('1') + '#' * 32000 + '\n', 'source_or_parser_limit'),
])
def test_source_and_parser_limits_return_bounded_failure_codes(candidate, rule):
    result = static._analyze(candidate)
    assert result['verdict'] == 'rejected' and result['issue']['rule'] == rule


def test_syntax_errors_never_echo_source_text():
    result = static._analyze(source("'PRIVATE-SECRET' +"))
    assert result['issue']['rule'] == 'python_syntax'
    assert 'PRIVATE-SECRET' not in canonical(result)


def test_review_requires_persisted_matching_preview_and_never_initializes_missing_journals(tmp_path, monkeypatch):
    budget = base(tmp_path, configured=True); directory = bundle(tmp_path)
    monkeypatch.setattr(static, '_analyze', lambda *a: pytest.fail('unregistered code must not be analyzed'))
    with pytest.raises(ValueError, match='existing migrated'): static.review(budget, directory, static.POLICY)
    assert not budget.path.exists()


def test_new_candidate_version_is_not_reviewed_using_another_versions_reservation(tmp_path, monkeypatch):
    budget, _ = registered(tmp_path); other = bundle(tmp_path, 'new-effect', candidate=source('2'))
    raw = budget.path.read_bytes()
    monkeypatch.setattr(static, '_analyze', lambda *a: pytest.fail('new effect needs its own preview reservation'))
    with pytest.raises(ValueError, match='matching completed'): static.review(budget, other, static.POLICY)
    assert budget.path.read_bytes() == raw


@pytest.mark.parametrize('exception', [RuntimeError, common.BudgetCancelled, common.BudgetTimedOut, SystemExit])
def test_failed_or_unfinished_preview_cannot_authorize_review(tmp_path, monkeypatch, exception):
    budget = migrated(tmp_path); directory = bundle(tmp_path)
    identity = {'candidate_identity_sha256': preview.read_preview(directory)['candidate_identity_sha256']}
    def fail(): raise exception('private')
    with pytest.raises((RuntimeError, SystemExit)): budget.run('code_check', identity, fail)
    raw = budget.path.read_bytes()
    monkeypatch.setattr(static, '_analyze', lambda *a: pytest.fail('failed preview'))
    with pytest.raises(ValueError, match='matching completed'): static.review(budget, directory, static.POLICY)
    assert budget.path.read_bytes() == raw


def test_completed_at_cap_review_is_read_only_and_preserves_original_cache_provenance(tmp_path):
    policy = {**common.DEFAULT_POLICY, 'total_actions': 2}
    budget, original = registered(tmp_path, policy=policy)
    copy = bundle(tmp_path, 'reworded', wording='Different hypothesis')
    raw, before = budget.path.read_bytes(), budget.snapshot()
    result = static.review(budget, copy, deepcopy(static.POLICY))
    assert result['analysis']['verdict'] == 'passed_static_contract'
    assert result['registration']['original_preview_sha256'] == preview.read_preview(original)['preview_sha256']
    assert result['registration']['original_preview_sha256'] != result['current_preview_sha256']
    assert result['registration']['database_read_only'] and result['registration']['new_common_actions'] == 0
    assert result['registration']['scope'] == 'existing_completed_preview_not_static_or_execution_reservation'
    assert not result['static_cost_in_common_resource_journal'] and not result['new_attempt_reserved']
    assert result['review_sha256'] == digest({k:v for k,v in result.items() if k != 'review_sha256'})
    assert budget.path.read_bytes() == raw and budget.snapshot() == before
    repeated = static.review(budget, copy, static.POLICY)
    assert repeated['analysis'] == result['analysis'] and repeated['registration'] == result['registration']
    assert budget.path.read_bytes() == raw


@pytest.mark.parametrize('change', ['checksum', 'executed_flag', 'fake_boolean', 'kind', 'input', 'usage', 'resources'])
def test_corrupt_or_semantically_forged_registration_is_rejected_without_repair(tmp_path, change):
    budget, directory = registered(tmp_path)
    with sqlite3.connect(budget.path) as db:
        if change in ('executed_flag', 'fake_boolean'):
            key, raw = db.execute("SELECT key,payload FROM coordinated_actions WHERE kind='code_check'").fetchone()
            envelope = json.loads(raw)
            envelope['result']['candidate_executed' if change == 'executed_flag' else 'attempt_budget_reserved'] = True if change == 'executed_flag' else 1
            db.execute('UPDATE coordinated_actions SET payload=?,payload_sha=? WHERE key=?', (canonical(envelope),digest(envelope),key))
        elif change == 'checksum': db.execute("UPDATE coordinated_actions SET payload_sha='bad' WHERE kind='code_check'")
        elif change == 'kind': db.execute("UPDATE coordinated_actions SET kind='fit' WHERE kind='code_check'")
        elif change == 'input': db.execute("UPDATE coordinated_actions SET input_sha='bad' WHERE kind='code_check'")
        elif change == 'usage': db.execute("UPDATE coordinated_actions SET observed='{}' WHERE kind='code_check'")
        else: db.execute("DELETE FROM coordinated_resources WHERE key IN (SELECT key FROM coordinated_actions WHERE kind='code_check')")
    raw = budget.path.read_bytes()
    with pytest.raises(ValueError): static.review(budget, directory, static.POLICY)
    assert budget.path.read_bytes() == raw


def test_registered_candidate_with_side_effect_is_parsed_and_rejected_without_execution(tmp_path):
    marker = tmp_path / 'never-create'
    candidate = source(f"open({str(marker)!r}, 'w').write('side effect')")
    budget, directory = registered(tmp_path, candidate=candidate)
    result = static.review(budget, directory, static.POLICY)
    assert result['analysis']['verdict'] == 'rejected' and not marker.exists()
    assert not result['analysis']['candidate_imported'] and not result['analysis']['candidate_executed']


@pytest.mark.parametrize('field,value', [('max_ast_nodes', 4096), ('max_window_candles', 1000),
    ('candidate_execution_enabled', True), ('candidate_execution_enabled', 0), ('output_key', 'target')])
def test_contract_cannot_be_widened_by_changing_json(tmp_path, field, value):
    budget, directory = registered(tmp_path); raw = budget.path.read_bytes()
    with pytest.raises(ValueError, match='fixed independent static contract'):
        static.review(budget, directory, {**static.POLICY, field:value})
    assert budget.path.read_bytes() == raw


def test_implementation_change_and_changed_preview_are_rejected(tmp_path, monkeypatch):
    budget, directory = registered(tmp_path)
    with monkeypatch.context() as altered:
        changed = deepcopy(static._LOADED); changed['static_checker'] = '0' * 64
        altered.setattr(static, '_LOADED', changed)
        with pytest.raises(ValueError, match='implementation changed'): static.review(budget, directory, static.POLICY)
    original = static._analyze
    def changed(source):
        result = original(source)
        (directory / 'candidate/research/feature_candidate.py').write_text('changed\n')
        return result
    monkeypatch.setattr(static, '_analyze', changed)
    with pytest.raises(ValueError, match='private source copy changed'): static.review(budget, directory, static.POLICY)


def test_cli_writes_private_review_of_registered_candidate_without_mutating_journal(tmp_path):
    budget, directory = registered(tmp_path)
    semantic = tmp_path / 'semantic-policy.json';semantic.write_text(canonical(DEFAULT_SEMANTIC_POLICY))
    code_policy = tmp_path / 'code-policy.json';code_policy.write_text(canonical(code.POLICY))
    static_policy = tmp_path / 'static-policy.json';static_policy.write_text(canonical(static.POLICY))
    output = tmp_path / 'review'
    args = ['--database',str(budget.path),'--proposal-ledger',str(tmp_path/'proposal.sqlite'),
        '--semantic-ledger',str(tmp_path/'semantic_fixture.sqlite'),'--fit-ledger',str(tmp_path/'fit.sqlite'),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),'--semantic-live-policy',str(semantic),
        '--code-policy',str(code_policy),'--preview',str(directory),'--static-policy',str(static_policy),'--directory',str(output)]
    raw = budget.path.read_bytes();assert static.main(args) == 0
    assert budget.path.read_bytes() == raw
    result = json.loads((output / 'review.json').read_text())
    assert result['analysis']['syntax_parsed'] and result['operational_database_connections'] == 0
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / 'review.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):static.main(args)


def test_checked_in_independent_contract_is_fixed():
    assert json.loads(Path('config/research-code-static-v1.json').read_text()) == static.POLICY
