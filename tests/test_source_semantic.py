from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading

import pytest

from cryptoforge import source_semantic_contracts as source, local_semantic_contracts as local
from cryptoforge import local_semantic_requests as journal_module, local_semantic_worker as worker
from cryptoforge import llm_research_coordinator as coordinator, semantic_source_snapshot as snapshots
from cryptoforge.research_training_diagnostics import canonical, digest
from cryptoforge.research_run_budget import DEFAULT_POLICY, BudgetCancelled, BudgetTimedOut
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY
from test_semantic_event_review import inputs, packet_for, response_for
from test_local_semantic import backend, make_coordinator, inner, transport_fixture, prepare as record_request
from test_ollama_systemone import catalog, response


@pytest.fixture
def case():
    snapshot, bundle = inputs()
    packet = packet_for(snapshot, bundle)
    return snapshot, bundle, packet


def request_for(case, endpoint='http://127.0.0.1:11434', **kwargs):
    return source.prepare_request(*case, endpoint=endpoint, digest_pin=kwargs.pop('digest_pin', 'd' * 64), **kwargs)


def provider_response(packet, confidence=0.9, **overrides):
    answers = response_for(packet, **overrides)['answers']
    for answer in answers.values(): answer['confidence'] = confidence
    return {'model': 'synthetic-replaced-with-pinned-reference', 'answers': answers,
            'usage': {'input_tokens': 123, 'output_tokens': 7}}


def source_transport(request, **overrides):
    result = transport_fixture(request, provider_response(request['packet'], **overrides))
    result['metadata']['response_received_at'] = result['metadata']['checked_at']
    return result


def call(research, case, **kwargs):
    return research.semantic_source(*case, digest_pin='d' * 64, **kwargs)


def test_closed_source_request_rebuilds_original_evidence_and_has_only_eligible_wire_state(case):
    original = deepcopy(case); request = request_for(case)
    assert local.validate_request(request) == request and source.validate_request(request) == request
    assert request['schema_version'] == source.SCHEMA and 'record' not in request
    assert request['wire_request']['state'] == case[2]['model_state']
    assert request['wire_request']['keep_alive'] == 0
    assert len(request['catalog']['questions']) == 6
    assert not request['hard_input_token_limit_verified'] and not request['upstream_development_lineage_verified']
    assert request['wire_bytes'] == len(canonical(request['wire_request']).encode()) <= 48000
    assert case == original
    assert 'minimum_confidence' not in canonical(request['wire_request'])
    assert 'registry_bundle' not in request['wire_request'] and 'snapshot' not in request['wire_request']


@pytest.mark.parametrize('part', ['snapshot', 'registry', 'packet', 'catalog', 'wire', 'implementation', 'origin', 'schema'])
def test_source_request_cannot_be_resealed_with_different_evidence_or_execution(case, part):
    request = request_for(case)
    if part == 'snapshot': request['snapshot']['observations'][0]['original_text'] += ' forged'
    elif part == 'registry': request['registry_bundle']['registry']['aliases'][0]['asset_id'] = 'test:forged'
    elif part == 'packet': request['packet']['model_state']['focus']['start'] += 1
    elif part == 'catalog': request['catalog']['questions']['asset']['minimum_confidence'] = 0
    elif part == 'wire': request['wire_request']['tools'] = [{'command': 'forbidden'}]
    elif part == 'implementation': request['implementation']['source_contracts'] = '0' * 64
    elif part == 'origin': request['origin'] = 'closed_validation_research_record'
    else: request['schema_version'] = 'local-semantic-request-v1'
    request['request_sha256'] = digest({k: v for k, v in request.items() if k != 'request_sha256'})
    with pytest.raises(ValueError): local.validate_request(request)


@pytest.mark.parametrize('kwargs', [
    {'version': '0.40.6'}, {'digest_pin': 'short'}, {'endpoint': 'https://ollama.com'},
    {'endpoint': 'http://localhost:11434'}, {'endpoint': 'http://127.0.0.1:11434/other'},
])
def test_source_backend_identity_is_explicit_and_local(case, kwargs):
    endpoint = kwargs.get('endpoint', 'http://127.0.0.1:11434')
    kwargs = {k: v for k, v in kwargs.items() if k != 'endpoint'}
    with pytest.raises(ValueError): request_for(case, endpoint, **kwargs)


def test_large_originals_fail_instead_of_dropping_future_evidence(case):
    snapshot, bundle, _ = case
    rows = [{k: r[k] for k in snapshots.ROW_FIELDS} for r in snapshot['observations']]
    for i in range(6):
        row = deepcopy(rows[0]); row['source_item_id'] = 'future-' + str(i)
        row['original_text'] = 'FUTURE ' + 'x' * 30000
        for key in ('first_seen_at', 'received_at', 'recorded_at'): row[key] = '2000-01-02T00:00:00+00:00'
        rows.append(row)
    later = snapshots.build_snapshot({'schema_version': 'semantic-source-export-v1', 'origin': 'synthetic',
        'partition': 'development', 'observations': rows}, snapshot['source_policy'])
    packet = packet_for(later, bundle)
    assert 'FUTURE' not in canonical(packet['model_state'])
    with pytest.raises(ValueError, match='including original evidence'):
        request_for((later, bundle, packet))


def test_real_loopback_worker_uses_same_fixed_routes_and_new_receipt_time(case):
    with backend(provider_response(case[2])) as (endpoint, calls, _):
        request = request_for(case, endpoint)
        transport = worker.run_worker(request, wall_seconds=3)
    assert [row['path'] for row in calls] == ['/api/version', '/api/show', '/v1/systemone', '/api/version']
    assert calls[2]['body'] == request['wire_request'] and all(row['authorization'] is None for row in calls)
    normalized = local.normalize_transport(request, transport)
    assert normalized['schema_version'] == source.RESULT_SCHEMA and 'record_sha256' not in normalized
    assert normalized['source_packet_sha256'] == case[2]['packet_sha256']
    assert normalized['metadata']['response_received_at'] <= normalized['metadata']['checked_at']
    assert not normalized['live_model_quality_evaluated']


def test_coordinator_reserves_both_journals_and_caches_same_packet(case, tmp_path, monkeypatch):
    research, _ = make_coordinator(tmp_path)
    with backend(provider_response(case[2])) as (endpoint, calls, _):
        first = call(research, case, endpoint=endpoint)
        monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('outer cache cannot run worker'))
        second = call(research, case, endpoint=endpoint)
    assert len(calls) == 4 and second['coordinator_cached']
    result = first['result']; review = result['source_event_review']
    assert review['status'] == 'review_required' and review['origin'] == 'ollama_local_systemone'
    assert review['source_origin'] == review['registry_origin'] == 'synthetic'
    assert review['annotation_proposal']['proposed_asset_id'] == 'test:AAA'
    assert review['annotation_proposal']['event_type'] == 'withdrawal_halt'
    assert review['annotation_proposal']['requires_human_review']
    assert review['judgment_received_at'] == result['metadata']['response_received_at']
    assert review['journal_finished_at'] == result['semantic_journal_finished_at']
    assert second['result'] == result and review['inference_available_at'] is None
    for flag in ('human_gold', 'context_grounding_verified', 'external_truth_verified', 'global_token_identity_verified',
                 'policy_calibrated', 'historical_feature_availability_verified', 'source_coverage_verified',
                 'event_labels_created', 'training_features_created', 'can_authorize_trades'):
        assert review[flag] is False
    snapshot = research.budget.snapshot()
    assert snapshot['reserved_by_kind'] == {'fit': 1, 'semantic_live': 1}
    assert snapshot['reserved_semantic_questions'] == 6
    assert first['original_resources']['tokens'] == {'input_tokens': 123, 'output_tokens': 7, 'total_tokens': 130}
    assert second['invocation_observed']['local_llm_completions'] == 0


def test_threshold_change_reuses_raw_response_without_changing_first_receipt(case, tmp_path, monkeypatch):
    research, _ = make_coordinator(tmp_path)
    with backend(provider_response(case[2], confidence=0.9)) as (endpoint, calls, _):
        first = call(research, case, endpoint=endpoint)
        changed = (*case[:2], packet_for(*case[:2], minimum_confidence=0.95))
        assert local.inference_identity(request_for(case, endpoint)) == local.inference_identity(request_for(changed, endpoint))
        monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('policy change must reuse raw response'))
        second = call(research, changed, endpoint=endpoint)
    assert len(calls) == 4 and not second['coordinator_cached'] and second['result']['semantic_cached']
    assert second['result']['source_event_review']['status'] == 'abstain'
    assert first['result']['source_event_review']['status'] == 'review_required'
    for field in ('judgment_received_at', 'journal_finished_at'):
        assert first['result']['source_event_review'][field] == second['result']['source_event_review'][field]
    assert second['invocation_observed']['local_llm_completions'] == 0
    assert second['invocation_resources']['tokens']['total_tokens'] == 0


@pytest.mark.parametrize('policy', [
    {**DEFAULT_POLICY, 'total_actions': 1}, {**DEFAULT_POLICY, 'semantic_questions': 5},
])
def test_common_cap_is_checked_before_inner_reservation_or_worker(case, tmp_path, monkeypatch, policy):
    research, _ = make_coordinator(tmp_path, policy=policy)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('must reject before worker'))
    with pytest.raises(ValueError): call(research, case)
    assert not research.live_path.exists()


def test_missing_migration_and_pre_cancel_do_not_create_inner_journal(case, tmp_path, monkeypatch):
    research, _ = make_coordinator(tmp_path, migrate=False)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('no worker'))
    with pytest.raises(ValueError, match='explicit semantic budget migration'): call(research, case)
    event = threading.Event(); event.set()
    with pytest.raises(BudgetCancelled): call(research, case, cancel_event=event)
    assert not research.live_path.exists()


def test_future_decision_is_rejected_before_budget_reservation(case, tmp_path):
    snapshot, bundle, _ = case
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    rows = [{k: r[k] for k in snapshots.ROW_FIELDS} for r in snapshot['observations']]
    for key in ('first_seen_at', 'received_at', 'recorded_at'): rows[0][key] = future
    snapshot = snapshots.build_snapshot({'schema_version': 'semantic-source-export-v1', 'origin': 'synthetic',
        'partition': 'development', 'observations': rows}, snapshot['source_policy'])
    packet = packet_for(snapshot, bundle, decision_time=future)
    research, _ = make_coordinator(tmp_path)
    with pytest.raises(ValueError, match='admission time'): call(research, (snapshot, bundle, packet))
    assert research.budget.snapshot()['total_reserved_actions'] == 1 and not research.live_path.exists()


@pytest.mark.parametrize('mode', ['wrong_model', 'unknown_question', 'invalid_usage', 'manifest_swap', 'version_drift'])
def test_transport_failures_stay_charged_in_both_journals_without_retry(case, tmp_path, mode):
    research, _ = make_coordinator(tmp_path)
    with backend(provider_response(case[2]), mode) as (endpoint, calls, _):
        with pytest.raises(RuntimeError): call(research, case, endpoint=endpoint)
        count = len(calls)
        with pytest.raises(ValueError, match='no automatic retry'): call(research, case, endpoint=endpoint)
        assert len(calls) == count
    assert research.budget.snapshot()['statuses'] == {'completed': 1, 'failed': 1}
    journal = inner_for(research)
    assert journal.snapshot()['statuses'] == {'failed': 1}


def inner_for(research):
    return journal_module.LocalSemanticRequests(research.live_path, {
        'common_path_sha256': digest(str(research.budget.path)),
        'semantic_configuration_sha256': digest(research.budget.semantic_configuration)}, clock=research.budget.clock)


def test_source_timeout_is_charged_without_retry(case, tmp_path):
    research, _ = make_coordinator(tmp_path)
    policy = {**journal_module.DEFAULT_POLICY, 'wall_seconds': 0.3}
    with backend(provider_response(case[2]), 'slow_headers') as (endpoint, calls, _):
        with pytest.raises(BudgetTimedOut): call(research, case, endpoint=endpoint, request_policy=policy)
        count = len(calls)
        with pytest.raises(ValueError, match='no automatic retry'):
            call(research, case, endpoint=endpoint, request_policy=policy)
        assert len(calls) == count
    assert research.budget.snapshot()['statuses'] == {'completed': 1, 'timed_out': 1}


def test_cancel_in_flight_charges_common_and_inner(case, tmp_path):
    research, _ = make_coordinator(tmp_path); event = threading.Event()
    with backend(provider_response(case[2]), 'slow_headers') as (endpoint, _, started):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(call, research, case, endpoint=endpoint, cancel_event=event)
            assert started.wait(3); event.set()
            with pytest.raises(BudgetCancelled): future.result(timeout=3)
    assert research.budget.snapshot()['statuses'] == {'completed': 1, 'cancelled': 1}
    assert inner_for(research).snapshot()['statuses'] == {'cancelled': 1}


def test_record_and_source_share_same_inner_request_limit(case, tmp_path, catalog, response, monkeypatch):
    journal = inner(tmp_path, policy={**journal_module.DEFAULT_POLICY, 'total_requests': 1})
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **k: transport_fixture(request, response))
    journal.evaluate(record_request(catalog))
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('shared inner quota exhausted'))
    with pytest.raises(ValueError, match='quota exhausted'): journal.evaluate(request_for(case))
    assert journal.snapshot()['total_requests'] == 1


def rewrite_execution_profile(journal, names):
    with sqlite3.connect(journal.path) as db:
        key, raw = db.execute('SELECT key,payload FROM local_semantic_requests').fetchone()
        payload = json.loads(raw)
        payload['execution']['implementation'] = {name: 'f' * 64 for name in names}
        db.execute('UPDATE local_semantic_requests SET payload=?,payload_sha=? WHERE key=?',
                   (canonical(payload), digest(payload), key))


def test_legacy_seven_file_receipt_remains_readable_without_model_repeat(tmp_path, catalog, response, monkeypatch):
    journal = inner(tmp_path); request = record_request(catalog)
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **k: transport_fixture(request, response))
    journal.evaluate(request); rewrite_execution_profile(journal, worker.LEGACY_SOURCE_NAMES)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('legacy cache must not execute'))
    assert journal.evaluate(request)['semantic_cached']


def test_source_cache_requires_source_dependency_profile_and_never_retries(case, tmp_path, monkeypatch):
    journal = inner(tmp_path); request = request_for(case)
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **k: source_transport(request))
    journal.evaluate(request); rewrite_execution_profile(journal, worker.LEGACY_SOURCE_NAMES)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('invalid cache must not execute'))
    with pytest.raises(ValueError, match='historical semantic source profile'): journal.evaluate(request)


@pytest.mark.parametrize('overrides,status', [
    ({'asset': 'no_match'}, 'no_match'), ({'event_state': 'unknown'}, 'abstain'),
    ({'event_state': 'not_stated'}, 'abstain'), ({'source_support': 'conflicting'}, 'abstain'),
    ({'evidence': 'no_match'}, 'abstain'), ({'market_scope': 'mixed'}, 'abstain'),
    ({'event_state': 'negated'}, 'review_required'), ({'message_kind': 'rumor'}, 'review_required'),
])
def test_source_answer_composition_preserves_abstention_and_claim_types(case, tmp_path, monkeypatch, overrides, status):
    journal = inner(tmp_path); request = request_for(case)
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **k: source_transport(request, **overrides))
    result = journal.evaluate(request)
    review = source.compose_review(request, result)
    assert review['status'] == status and not review['event_labels_created']
    if status == 'review_required':
        for key in ('event_state', 'message_kind'):
            if key in overrides: assert review['annotation_proposal'][key] == overrides[key]


def test_missing_and_invalid_source_answers_abstain_after_valid_transport(case, tmp_path, monkeypatch):
    journal = inner(tmp_path); request = request_for(case)
    transport = source_transport(request)
    transport['response']['answers'].pop('event_state')
    transport['response']['answers']['evidence']['choice'] = 'invented_quote'
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: transport)
    result = journal.evaluate(request)
    assert source.compose_review(request, result)['status'] == 'abstain'
    assert journal.snapshot()['statuses'] == {'completed': 1}


@pytest.mark.parametrize('field', ['origin', 'state_sha256', 'source_packet_sha256', 'question_catalog_sha256'])
def test_result_cannot_be_rebound_or_relabelled_from_mock(case, tmp_path, monkeypatch, field):
    journal = inner(tmp_path); request = request_for(case)
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **k: source_transport(request))
    result = journal.evaluate(request); result[field] = 'mock' if field == 'origin' else '0' * 64
    with pytest.raises(ValueError): source.compose_review(request, result)


def test_missing_or_reversed_response_receipt_is_rejected(case):
    request = request_for(case)
    transport = source_transport(request); transport['metadata'].pop('response_received_at')
    with pytest.raises(ValueError): local.normalize_transport(request, transport)


def test_response_cannot_predate_source_decision(case):
    request = request_for(case); transport = source_transport(request)
    transport['metadata']['response_received_at'] = '1999-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='precedes source decision'): local.normalize_transport(request, transport)
    transport = source_transport(request); transport['metadata']['response_received_at'] = '2999-01-01T00:00:00Z'
    with pytest.raises(ValueError): local.normalize_transport(request, transport)


def test_source_cli_requires_explicit_migrated_budget_before_output(tmp_path):
    with pytest.raises(SystemExit):
        coordinator.main(['--proposal-ledger', str(tmp_path/'p'), '--semantic-ledger', str(tmp_path/'s'),
            '--fit-ledger', str(tmp_path/'f'), '--output', str(tmp_path/'receipt.json'), 'semantic-source',
            '--snapshot', 'unused', '--registry', 'unused', '--packet', 'unused', '--model-digest', 'd' * 64])
    assert not (tmp_path/'receipt.json').exists()


def test_source_cli_uses_bound_existing_journals_and_private_receipt(case, tmp_path):
    research, _ = make_coordinator(tmp_path)
    snapshot, bundle, packet = case
    registry_path = tmp_path/'registry'; registry_path.mkdir()
    for name, value in (('snapshot', snapshot), ('packet', packet), ('semantic-policy', DEFAULT_SEMANTIC_POLICY)):
        (tmp_path/(name+'.json')).write_text(canonical(value))
    for name in ('registry', 'registration'): (registry_path/(name+'.json')).write_text(canonical(bundle[name]))
    output = tmp_path/'receipt.json'
    common = ['--database', str(research.budget.path), '--proposal-ledger', str(research.paths['proposal']),
        '--semantic-ledger', str(research.paths['semantic_fixture']), '--fit-ledger', str(research.paths['fit']),
        '--semantic-live-ledger', str(research.live_path), '--semantic-live-policy', str(tmp_path/'semantic-policy.json'),
        '--output', str(output), 'semantic-source', '--snapshot', str(tmp_path/'snapshot.json'),
        '--registry', str(registry_path), '--packet', str(tmp_path/'packet.json'), '--model-digest', 'd' * 64]
    with backend(provider_response(packet)) as (endpoint, calls, _):
        args = [*common, '--endpoint', endpoint]
        assert coordinator.main(args) == 0
        assert len(calls) == 4
        with pytest.raises(FileExistsError): coordinator.main(args)
    receipt = json.loads(output.read_text())
    assert output.stat().st_mode & 0o777 == 0o600 and receipt['status'] == 'completed'
    assert receipt['call']['result']['source_event_review']['status'] == 'review_required'
