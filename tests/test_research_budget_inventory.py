"""Readonly native budget replay, nullable usage and ambiguous cross-journal history."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from cryptoforge import research_budget_inventory as m
from cryptoforge.research_attempts import ResearchAttempts
from test_llm_advice_provenance import origin
from test_research_phase import migrated


def ref(path, kind, identity, options=None):
    return {'id': identity, 'kind': kind, 'path': str(path.resolve()),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'options': options or {}}


@pytest.fixture
def inventory_request(tmp_path):
    api_dir = tmp_path/'api'; api_dir.mkdir()
    _, _, api, _, _ = origin(api_dir)
    legacy = tmp_path/'attempts.sqlite'; ledger = ResearchAttempts(legacy)
    manifest = {'dataset': 'synthetic', 'grid': [{'family': 'trend', 'value': 1}]}
    study = ledger.register(manifest, protocol_id='fixture-protocol', maximum_per_family=1)
    ledger.record(study, manifest['grid'][0], {'synthetic': True})
    replay = tmp_path/'replay.sqlite'; shutil.copy2(legacy, replay)
    return {'schema_version': 'research-budget-inventory-request-v1', 'scope': m.POLICY['scope'],
        'journals': [ref(api, 'api', 'api'), ref(legacy, 'attempts', 'original'), ref(replay, 'attempts', 'replay')]}


def test_visible_totals_are_not_summed_or_deduplicated_by_guess(inventory_request):
    before = {item['path']: Path(item['path']).read_bytes() for item in inventory_request['journals']}
    report = m.collect(inventory_request, '2026-10-23T17:00:00Z')
    api = report['journals'][0]
    assert api['reserved_requests'] == 1 and api['statuses'] == {'completed': 1}
    assert api['known_provider_token_subtotal'] == {'input_tokens': 50, 'output_tokens': 20, 'total_tokens': 0}
    assert api['unknown_token_rows_by_field']['total_tokens'] == 1
    assert api['records'][0]['recorded_zero_pricing'] is True
    assert api['records'][0]['billing_usd_verified'] is None
    assert report['byte_identical_journal_groups'] == [['original', 'replay']]
    assert len(report['overlapping_attempt_identity_groups']) == 1
    assert report['cross_journal_global_totals'] is None and report['account_wide_spend_usd'] is None
    assert not report['deduplication_or_double_charging_resolved']
    assert all(Path(path).read_bytes() == raw for path, raw in before.items())
    assert 'private-key' not in m.canonical(report)
    for name in ('jobpilot_shared_quota_verified', 'cpu_ram_disk_server_cli_cost_complete', 'billing_audited',
                 'journal_copied_migrated_reset_or_refunded', 'provider_called', 'fit_performed',
                 'model_prediction_performed', 'execution_authorized', 'production_promotion_authorized'):
        assert report[name] is False


def test_pending_api_attempt_retains_reservation_with_unknown_tokens(inventory_request):
    item = inventory_request['journals'][0]
    with sqlite3.connect(item['path']) as db:
        db.execute("UPDATE advisor_requests SET status='reserved',payload=NULL,payload_sha256=NULL")
    item['sha256'] = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
    report = m.collect(inventory_request, '2026-10-23T17:00:00Z')['journals'][0]
    assert report['reserved_requests'] == 1 and report['statuses'] == {'reserved': 1}
    assert all(value == 1 for value in report['unknown_token_rows_by_field'].values())
    assert all(value is None for value in report['records'][0]['tokens'].values())


def test_native_phase_snapshot_does_not_initialize_absent_bound_journals(tmp_path):
    budget, _, _ = migrated(tmp_path)
    parent = budget.path.parent
    # Reconstruct the exact persisted bindings used by the fixture.
    from test_research_run_budget import bindings
    options = {'bindings': bindings(tmp_path), 'semantic_live_ledger': str(tmp_path/'live.sqlite')}
    options['bindings'] = {key: str(value) for key, value in options['bindings'].items()}
    # The fixture exposes its original semantic configuration as a path hash.
    # Its actual source path is fixed in the shared registered fixture.
    import test_research_code_static as registered
    # Resolve only candidate names by the stored path hash, without creating files.
    candidates = [tmp_path/'live.sqlite', tmp_path/'semantic-live.sqlite', tmp_path/'live', tmp_path/'semantic-live']
    matched = [path for path in candidates if m.digest(str(path.resolve())) == budget.legacy.semantic_configuration['journal_path_sha256']]
    assert len(matched) == 1
    options['semantic_live_ledger'] = str(matched[0])
    item = ref(budget.path, 'common_v5', 'common', options)
    inventory_request = {'schema_version': 'research-budget-inventory-request-v1', 'scope': m.POLICY['scope'], 'journals': [item]}
    before = budget.path.read_bytes(); report = m.collect(inventory_request, '2026-10-23T17:00:00Z')['journals'][0]
    assert report['native_snapshot']['numeric_control_cache_only']
    assert report['native_snapshot']['numeric_control_lifetime_limit'] == 3
    assert budget.path.read_bytes() == before
    assert not any(report['original_binding_files_present'].values())


def test_fixture_budget_tokens_are_not_treated_as_billed_provider_usage(tmp_path):
    path = tmp_path/'semantic.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE semantic_policy (id INTEGER PRIMARY KEY,payload TEXT,sha TEXT);'
            'CREATE TABLE semantic_requests (key TEXT,request_sha TEXT,fixture_sha TEXT,utc_day TEXT,questions INTEGER,'
            'status TEXT,reserved_at TEXT,finished_at TEXT,payload TEXT,payload_sha TEXT,safe_error TEXT);')
        db.execute('INSERT INTO semantic_policy VALUES (1,?,?)', (m.canonical(m.semantic.DEFAULT_POLICY),m.digest(m.semantic.DEFAULT_POLICY)))
    path.chmod(0o600)
    inventory_request = {'schema_version': 'research-budget-inventory-request-v1', 'scope': m.POLICY['scope'],
        'journals': [ref(path, 'semantic_fixture', 'fixture')]}
    snapshot = m.collect(inventory_request, '2026-10-23T17:00:00Z')['journals'][0]['native_snapshot']
    assert snapshot['origin'] == 'offline_sdk_fixture' and snapshot['api_calls'] == 0
    assert snapshot['total_requests'] == 0


def test_attempt_inventory_never_uses_legacy_writer_initializer(inventory_request, monkeypatch):
    monkeypatch.setattr(ResearchAttempts, '_db', lambda *_: pytest.fail('readonly inventory cannot initialize schema'))
    report = m.collect(inventory_request, '2026-10-23T17:00:00Z')
    assert len(report['journals']) == 3 and report['new_budget_actions'] == 0


@pytest.mark.parametrize('change', [
    lambda r: r.update(scope='account_wide_complete'),
    lambda r: r['journals'][0].update(sha256='a'*64),
    lambda r: r['journals'][0].update(id='../secret'),
    lambda r: r['journals'][0].update(kind='postgres_live'),
    lambda r: r['journals'][0].update(options={'migrate': True}),
    lambda r: r['journals'].append(deepcopy(r['journals'][0])),
    lambda r: r['journals'][0].update(path='./api.sqlite'),
])
def test_input_scope_identity_and_source_guards(inventory_request, change):
    change(inventory_request)
    with pytest.raises(ValueError): m.collect(inventory_request, '2026-10-23T17:00:00Z')


def test_hot_sidecar_is_refused_without_touching_original_journal(inventory_request):
    path = Path(inventory_request['journals'][0]['path']); sidecar = Path(str(path)+'-journal'); sidecar.write_bytes(b'pending')
    with pytest.raises(ValueError, match='inactive_delete_mode'): m.collect(inventory_request, '2026-10-23T17:00:00Z')
    assert sidecar.read_bytes() == b'pending'


def test_wrong_schema_is_not_silently_treated_as_an_empty_ledger(inventory_request):
    item = inventory_request['journals'][0]
    with sqlite3.connect(item['path']) as db: db.execute('CREATE TABLE extra (x TEXT)')
    item['sha256'] = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='closed_budget_journal_schema'): m.collect(inventory_request, '2026-10-23T17:00:00Z')


def test_rehashed_source_does_not_hide_response_checksum_corruption(inventory_request):
    item = inventory_request['journals'][0]
    with sqlite3.connect(item['path']) as db: db.execute("UPDATE advisor_requests SET payload_sha256='bad'")
    item['sha256'] = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='payload_checksum'): m.collect(inventory_request, '2026-10-23T17:00:00Z')


def test_changed_source_during_inventory_is_refused(inventory_request, monkeypatch):
    original = m._pinned; calls = []
    def checked(item):
        result = original(item); calls.append(item['id'])
        if calls == ['api']:
            with sqlite3.connect(item['path']) as db: db.execute('UPDATE request_policy SET maximum=4')
        return result
    monkeypatch.setattr(m, '_pinned', checked)
    with pytest.raises(ValueError, match='original_budget_journal_checksum_changed'):
        m.collect(inventory_request, '2026-10-23T17:00:00Z')


def test_private_pack_recomputes_from_original_journals_and_rejects_forgery(inventory_request, tmp_path):
    report = m.prepare(tmp_path/'pack', inventory_request)
    assert m.verify(tmp_path/'pack') == report
    assert (tmp_path/'pack').stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (tmp_path/'pack').iterdir())
    with pytest.raises(ValueError, match='new_budget_inventory'): m.prepare(tmp_path/'pack', inventory_request)
    report['account_wide_spend_usd'] = 0
    report['inventory_sha256'] = m.digest({key: value for key, value in report.items() if key != 'inventory_sha256'})
    (tmp_path/'pack/inventory.json').write_text(m.canonical(report)+'\n')
    with pytest.raises(ValueError, match='budget_inventory_or_original_sources_changed'): m.verify(tmp_path/'pack')


def test_policy_config_and_safe_cli_refusal(tmp_path, capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-budget-inventory-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret-path')]) == 2
    assert 'private-secret-path' not in capsys.readouterr().out
