from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pytest

from cryptoforge import semantic_source_snapshot as sources
from cryptoforge.research_training_diagnostics import canonical, digest


T0 = '2026-10-18T10:00:00+00:00'
T1 = '2026-10-18T10:01:00+00:00'
T2 = '2026-10-18T10:02:00+00:00'
T3 = '2026-10-18T10:03:00+00:00'
T4 = '2026-10-18T10:04:00+00:00'


@pytest.fixture
def policy():
    return json.loads((Path(__file__).resolve().parents[1]/'config/semantic-source-policy-v1.json').read_text())


@pytest.fixture
def row():
    return {'source_id':'bybit-announcements', 'source_item_id':'synthetic-notice',
        'source_url':'https://announcements.bybit.com/en/article/synthetic-notice/',
        'title':'SYNTHETIC notice', 'original_text':'SYNTHETIC: withdrawals are paused; trading is not mentioned.',
        'published_at':T0, 'source_revision':None, 'revised_at':None,
        'first_seen_at':T0, 'received_at':T1, 'recorded_at':T2, 'capture_sha256':'a'*64}


def export(*rows):
    return {'schema_version':'semantic-source-export-v1', 'origin':'synthetic',
            'partition':'development', 'observations':list(rows)}


def packet(policy, *rows):
    return sources.build_snapshot(export(*rows), policy)


def test_availability_is_latest_local_capture_not_backdated_publication(policy, row):
    snapshot = packet(policy, row)
    observed = snapshot['observations'][0]
    assert observed['available_at'] == T2
    assert sources.as_of(snapshot, decision_time=T1, ttl_seconds=600)['model_state'] == {'texts':[]}
    view = sources.as_of(snapshot, decision_time=T2, ttl_seconds=600)
    assert len(view['documents']) == len(view['model_state']['texts']) == 1
    assert view['documents'][0]['original_text'] == row['original_text']
    assert not view['asset_mapping_performed'] and not view['semantic_event_clusters_verified']
    assert not snapshot['upstream_development_lineage_verified']
    assert snapshot['capture_hash_assurance'] == 'declared_upstream_hash_not_raw_artifact_verification'
    assert snapshot['snapshot_sha256'] == digest({k:v for k,v in snapshot.items() if k != 'snapshot_sha256'})


@pytest.mark.parametrize('missing', ['first_seen_at','received_at','recorded_at'])
def test_unknown_capture_time_is_quarantined_never_inferred(policy, row, missing):
    row[missing] = None
    snapshot = packet(policy, row)
    assert snapshot['observations'][0]['available_at'] is None
    assert snapshot['observations'][0]['availability_status'] == 'unknown_local_capture_time'
    view = sources.as_of(snapshot, decision_time=T4, ttl_seconds=600)
    assert view['documents'] == view['abstentions'] == []
    assert view['model_state'] == {'texts':[]}
    assert not view['source_coverage_verified'] and not view['empty_view_is_negative_label']


def test_unknown_publication_can_use_known_capture_but_future_revision_waits(policy, row):
    row['published_at'] = None
    assert packet(policy, row)['observations'][0]['available_at'] == T2
    row['revised_at'] = T4
    snapshot = packet(policy, row)
    assert snapshot['observations'][0]['available_at'] == T4
    assert sources.as_of(snapshot, decision_time=T3, ttl_seconds=600)['model_state'] == {'texts':[]}


def test_future_corrections_cannot_rewrite_past_state_or_add_future_counts(policy, row):
    original = packet(policy, row)
    revision = {**row, 'original_text':'SYNTHETIC CORRECTION: trading will also stop.',
                'source_revision':'rev-2', 'revised_at':T0, # provider may backdate it
                'first_seen_at':T3, 'received_at':T3, 'recorded_at':T4, 'capture_sha256':'b'*64}
    new_item = {**revision, 'source_item_id':'future-new-item'}
    expanded = packet(policy, row, revision, new_item)
    before = sources.as_of(original, decision_time=T2, ttl_seconds=600)
    after = sources.as_of(expanded, decision_time=T2, ttl_seconds=600)
    assert before['model_state'] == after['model_state']
    assert before['model_state_sha256'] == after['model_state_sha256']
    assert before['documents'] == after['documents']
    assert 'CORRECTION' not in canonical(after)
    assert not any('excluded' in key or 'future_count' in key for key in after)
    current = sources.as_of(expanded, decision_time=T4, ttl_seconds=600)
    assert len(current['documents']) == 2
    assert all('CORRECTION' in r['original_text'] for r in current['documents'])
    assert len(current['model_state']['texts']) == 1


def test_same_timestamp_conflicting_revision_abstains_without_older_fallback(policy, row):
    a = {**row, 'recorded_at':T3, 'original_text':'SYNTHETIC correction A'}
    b = {**a, 'original_text':'SYNTHETIC correction B', 'capture_sha256':'b'*64}
    snapshot = packet(policy, row, a, b)
    view = sources.as_of(snapshot, decision_time=T4, ttl_seconds=600)
    assert view['documents'] == [] and view['model_state'] == {'texts':[]}
    assert view['abstentions'][0]['reason'] == 'ambiguous_revision'
    assert len(view['abstentions'][0]['observation_ids']) == 2


def test_revision_labels_are_not_sort_keys_and_late_old_text_is_known_reversion(policy, row):
    first = {**row, 'source_revision':'999'}
    second = {**row, 'original_text':'SYNTHETIC correction', 'source_revision':'1',
              'first_seen_at':T3, 'received_at':T3, 'recorded_at':T3}
    snap = packet(policy, first, second)
    assert sources.as_of(snap, decision_time=T3, ttl_seconds=600)['documents'][0]['source_revision'] == '1'
    reversion = {**row, 'source_revision':'0', 'first_seen_at':T4, 'received_at':T4, 'recorded_at':T4}
    view = sources.as_of(packet(policy, first, second, reversion), decision_time=T4, ttl_seconds=600)
    assert view['documents'][0]['original_text'] == row['original_text']
    assert view['documents'][0]['content_first_available_at'] == T2


def test_exact_duplicates_keep_provenance_and_unchanged_copies_do_not_refresh_ttl(policy, row):
    recapture = {**row, 'first_seen_at':T3, 'received_at':T3, 'recorded_at':T3, 'capture_sha256':'b'*64}
    copy = {**recapture, 'source_item_id':'synthetic-copy',
            'source_url':'https://announcements.bybit.com/en/article/synthetic-copy/'}
    snapshot = packet(policy, row, row, recapture, copy)
    assert len(snapshot['observations']) == 4 # retain all original evidence
    view = sources.as_of(snapshot, decision_time=T3, ttl_seconds=60)
    assert len(view['documents']) == 2 and len(view['model_state']['texts']) == 1
    assert len(view['model_state']['texts'][0]['document_ids']) == 2
    expired = sources.as_of(snapshot, decision_time=T4, ttl_seconds=60)
    assert expired['model_state'] == {'texts':[]}
    assert len(expired['abstentions']) == 2
    assert all(r['reason'] == 'expired_exact_content' for r in expired['abstentions'])


def test_whitespace_title_and_text_are_not_semantic_deduplicated(policy, row):
    other = {**row, 'source_item_id':'different-format', 'original_text':row['original_text']+' '}
    view = sources.as_of(packet(policy, row, other), decision_time=T3, ttl_seconds=600)
    assert len(view['model_state']['texts']) == 2
    changed = {**row, 'title':'Another title'}
    assert packet(policy, row)['observations'][0]['content_sha256'] != packet(policy, changed)['observations'][0]['content_sha256']


def test_normalized_times_and_input_permutations_produce_identical_snapshot(policy, row):
    other = {**row, 'source_item_id':'other', 'original_text':'Another SYNTHETIC text'}
    before = deepcopy((policy, row, other))
    left, right = packet(policy, row, other), packet(policy, other, row)
    assert left == right
    local = {**row, 'recorded_at':'2026-10-18T13:02:00+03:00'}
    assert packet(policy, local) == packet(policy, row)
    assert before == (policy, row, other)


@pytest.mark.parametrize('change', ['naive','date_only','bad_time','receive_before_seen','commit_before_receive',
    'revision_before_publication','unknown_source','userinfo','query','fragment','wrong_host','subdomain','http',
    'port','backslash','oversize_text','canonical_overflow','empty_text','bad_capture','extra_label','extra_target'])
def test_invalid_or_unbounded_capture_is_refused(policy, row, change):
    if change == 'naive': row['received_at'] = '2026-10-18T10:01:00'
    elif change == 'date_only': row['published_at'] = '2026-10-18'
    elif change == 'bad_time': row['recorded_at'] = True
    elif change == 'receive_before_seen': row['first_seen_at'] = T2
    elif change == 'commit_before_receive': row['recorded_at'] = T0
    elif change == 'revision_before_publication': row.update(published_at=T1, revised_at=T0)
    elif change == 'unknown_source': row['source_id'] = 'unknown'
    elif change == 'userinfo': row['source_url'] = 'https://u:p@announcements.bybit.com/article/'
    elif change == 'query': row['source_url'] += '?token=private'
    elif change == 'fragment': row['source_url'] += '#private'
    elif change == 'wrong_host': row['source_url'] = 'https://announcements.bybit.com.evil.test/article/'
    elif change == 'subdomain': row['source_url'] = 'https://sub.announcements.bybit.com/article/'
    elif change == 'http': row['source_url'] = row['source_url'].replace('https:', 'http:')
    elif change == 'port': row['source_url'] = 'https://announcements.bybit.com:443/article/'
    elif change == 'backslash': row['source_url'] += '\\other'
    elif change == 'oversize_text': row['original_text'] = 'x'*32001
    elif change == 'canonical_overflow': row['original_text'] = '\x00'*11000
    elif change == 'empty_text': row['original_text'] = '  '
    elif change == 'bad_capture': row['capture_sha256'] = 'a'*12
    elif change == 'extra_label': row['sentiment'] = 'positive'
    else: row['future_return'] = 0.1
    with pytest.raises(ValueError): packet(policy, row)


@pytest.mark.parametrize('change', ['partition','origin','origin_list','empty','too_many','schema'])
def test_invalid_export_never_becomes_source_state(policy, row, change):
    data = export(row)
    if change == 'partition': data['partition'] = 'test'
    elif change == 'origin': data['origin'] = 'model_generated_as_real'
    elif change == 'origin_list': data['origin'] = ['collector_export']
    elif change == 'empty': data['observations'] = []
    elif change == 'too_many': data['observations'] *= 1001
    else: data['schema_version'] = 'unversioned'
    with pytest.raises(ValueError): sources.build_snapshot(data, policy)


def test_collector_origin_is_declaration_and_never_real_backend_or_verified_lineage(policy, row):
    data = export(row); data['origin'] = 'collector_export'
    snapshot = sources.build_snapshot(data, policy)
    view = sources.as_of(snapshot, decision_time=T3, ttl_seconds=600)
    assert view['origin'] == 'collector_export'
    assert not view['upstream_development_lineage_verified']
    assert view['api_calls'] == 0 and not view['training_executed']


def test_view_limit_refuses_without_truncating_source(policy, row, monkeypatch):
    snapshot = packet(policy, row)
    before = deepcopy(snapshot)
    monkeypatch.setattr(sources, 'MAX_VIEW_BYTES', 500)
    with pytest.raises(ValueError, match='no truncation'):
        sources.as_of(snapshot, decision_time=T3, ttl_seconds=600)
    assert snapshot == before


@pytest.mark.parametrize('change', ['checksum','availability','text','policy','implementation'])
def test_snapshot_tampering_refused_before_selection(policy, row, change):
    snap = packet(policy, row)
    if change == 'checksum': snap['snapshot_sha256'] = 'b'*64
    elif change == 'availability': snap['observations'][0]['available_at'] = T0
    elif change == 'text': snap['observations'][0]['original_text'] = 'tampered'
    elif change == 'policy': snap['source_policy']['sources']['bybit-announcements']['allowed_hosts'] = ['example.com']
    else: snap['implementation']['source_snapshot'] = 'b'*64
    with pytest.raises(ValueError): sources.as_of(snap, decision_time=T3, ttl_seconds=600)


@pytest.mark.parametrize('ttl', [0, -1, True, 1.5, 604801, None])
def test_ttl_must_be_bounded_integer(policy, row, ttl):
    with pytest.raises(ValueError): sources.as_of(packet(policy, row), decision_time=T3, ttl_seconds=ttl)


def test_cli_round_trip_private_output_no_network_process_or_overwrite(policy, row, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('network/process execution refused')
    monkeypatch.setattr(socket, 'socket', forbidden); monkeypatch.setattr(subprocess, 'Popen', forbidden)
    source, config, snapshot, view = [tmp_path/name for name in ('source.json','policy.json','snapshot.json','view.json')]
    source.write_text(json.dumps(export(row))); config.write_text(json.dumps(policy))
    args = ['--output',str(snapshot),'snapshot','--export',str(source),'--policy',str(config)]
    assert sources.main(args) == 0
    data = snapshot.read_bytes()
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert sources.main(['--output',str(view),'as-of','--snapshot',str(snapshot),
                         '--decision-time',T3,'--ttl-seconds','600']) == 0
    assert view.stat().st_mode & 0o777 == 0o600
    result = json.loads(view.read_text())
    assert result['api_calls'] == 0 and not result['training_executed']
    with pytest.raises(FileExistsError): sources.main(args)
    assert snapshot.read_bytes() == data
    assert sorted(p.name for p in tmp_path.iterdir()) == ['policy.json','snapshot.json','source.json','view.json']


def test_duplicate_json_and_large_file_rejected_without_artifact(tmp_path):
    source, config, output = [tmp_path/name for name in ('source.json','policy.json','output.json')]
    source.write_text('{"schema_version":1,"schema_version":2}')
    config.write_text('{}')
    with pytest.raises(ValueError):
        sources.main(['--output',str(output),'snapshot','--export',str(source),'--policy',str(config)])
    assert not output.exists()
    source.write_text(' '*8000001)
    with pytest.raises(ValueError): sources._read(source, sources.MAX_EXPORT_BYTES)
