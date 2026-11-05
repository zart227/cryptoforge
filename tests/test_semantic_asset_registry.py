from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pytest

from cryptoforge import semantic_asset_registry as assets, semantic_source_collector as collector
from cryptoforge import semantic_source_snapshot as snapshots
from cryptoforge.training_diagnostics import canonical, digest


T0,T1,T2 = ['2000-01-01T00:00:0'+str(i)+'+00:00' for i in range(3)]
REGISTERED = '2000-01-01T00:01:00+00:00'
BEFORE = '2000-01-01T00:00:59+00:00'
TEXT = '🔎 SYNTHETIC AAA AAAUSDT BBB BBBUSDT Shared Name MYSTERYUSDT 10USDT ONE is a word.'


@pytest.fixture
def evidence():
    return [{'raw_sha256':'a'*64,'source_recorded_at':T2,
        'source_url':'https://announcements.bybit.com/en/article/synthetic-assets/',
        'title':'SYNTHETIC assets','original_text':TEXT,'receipt_sha256':'b'*64,'commit_sha256':'c'*64}]


@pytest.fixture
def definition():
    return {'schema_version':'semantic-asset-definitions-v1','registry_version':'synthetic-v1',
        'origin':'synthetic','assets':[{'asset_id':'test:'+t,'ticker':t,'aliases':[
            {'surface':t,'kind':'ticker','capture_sha256':'a'*64},
            {'surface':t+'USDT','kind':'pair','capture_sha256':'a'*64},
            {'surface':'Shared Name','kind':'name','capture_sha256':'a'*64}]} for t in ['AAA','BBB']]}


def bundle_for(definition,evidence,registered=REGISTERED):
    registry = assets._compile(definition,evidence)
    commit = collector._seal({'schema_version':'semantic-asset-registration-v1',
        'registry_sha256':registry['registry_sha256'],'registered_at':registered,
        'time_assurance':'local_after_registry_fsync_not_external_clock_attestation'},'registration_sha256')
    return {'registry':registry,'registration':commit}


@pytest.fixture
def bundle(definition,evidence):
    return bundle_for(definition,evidence)


def snapshot():
    policy = {'schema_version':'semantic-source-policy-v1','policy_version':'synthetic-v1',
              'sources':{'bybit-announcements':{'allowed_hosts':['announcements.bybit.com']}}}
    row = {'source_id':'bybit-announcements','source_item_id':'synthetic-assets',
        'source_url':'https://announcements.bybit.com/en/article/synthetic-assets/','title':'SYNTHETIC assets',
        'original_text':TEXT,'published_at':T0,'source_revision':None,'revised_at':None,
        'first_seen_at':T0,'received_at':T1,'recorded_at':T2,'capture_sha256':'a'*64}
    return snapshots.build_snapshot({'schema_version':'semantic-source-export-v1','origin':'synthetic',
                                    'partition':'development','observations':[row]},policy)


def test_unique_alias_remains_lexical_candidate_and_has_bound_provenance(bundle):
    result = assets.lookup(bundle,surface='AAAUSDT',kind='pair',decision_time=REGISTERED)
    assert result['status'] == 'unique_alias' and result['candidate_asset_id'] == 'test:AAA'
    assert result['resolved_asset_id'] is None and result['requires_context_review']
    assert not result['context_grounding_verified'] and not result['can_authorize_trades']
    assert result['registry_origin'] == 'synthetic' and result['api_calls'] == 0
    assert result['registration_sha256'] == bundle['registration']['registration_sha256']
    assert result['lookup_sha256'] == digest({k:v for k,v in result.items() if k != 'lookup_sha256'})


def test_shared_alias_ambiguous_never_selects_first_sorted_asset(bundle):
    result = assets.lookup(bundle,surface='Shared Name',kind='name',decision_time=REGISTERED)
    assert result['status'] == 'ambiguous' and result['candidates'] == ['test:AAA','test:BBB']
    assert result['candidate_asset_id'] is None and result['resolved_asset_id'] is None


def test_pair_alias_collision_is_also_ambiguous(definition,evidence):
    clone = deepcopy(definition['assets'][0]); clone['asset_id'] = 'test:AAA-reused'
    definition['assets'].append(clone)
    result = assets.lookup(bundle_for(definition,evidence),surface='AAAUSDT',kind='pair',decision_time=REGISTERED)
    assert result['status'] == 'ambiguous' and result['candidate_asset_id'] is None


@pytest.mark.parametrize('surface,kind', [('ZZZ','ticker'),('aaa','ticker'),('AAA/USDT','pair'),
    ('AAAUSDC','pair'),('AAA','name'),('АAA','ticker'),('AAAUSDT ','pair')])
def test_missing_kind_case_spacing_quote_or_unicode_variant_is_unknown(bundle,surface,kind):
    result = assets.lookup(bundle,surface=surface,kind=kind,decision_time=REGISTERED)
    assert result['status'] == 'unknown' and result['candidates'] == [] and result['candidate_asset_id'] is None


def test_registry_cannot_backdate_mapping_to_old_capture_time(bundle):
    for at in [T0,T2,BEFORE]:
        result = assets.lookup(bundle,surface='AAAUSDT',kind='pair',decision_time=at)
        assert result['status'] == 'unknown' and result['candidates'] == []
    assert assets.lookup(bundle,surface='AAAUSDT',kind='pair',decision_time=REGISTERED)['status'] == 'unique_alias'


def test_source_spans_are_exact_unicode_codepoint_offsets_and_keep_unknowns(bundle):
    result = assets.resolve_snapshot(snapshot(),bundle,decision_time=REGISTERED,ttl_seconds=600)
    assert result['source_origin'] == result['registry_origin'] == 'synthetic'
    rows = result['mentions']
    for row in rows:
        original = TEXT if row['field'] == 'original_text' else 'SYNTHETIC assets'
        assert original[row['start']:row['end']] == row['lookup']['surface']
        assert row['field_sha256'] == digest(original) and row['offset_unit'] == 'unicode_code_points'
    statuses = {r['lookup']['surface']:r['lookup']['status'] for r in rows}
    assert statuses['AAAUSDT'] == 'unique_alias' and statuses['Shared Name'] == 'ambiguous'
    assert statuses['MYSTERYUSDT'] == statuses['10USDT'] == 'unknown'
    assert all(r['lookup']['resolved_asset_id'] is None for r in rows)
    assert not result['lexical_coverage_verified'] and not result['event_labels_created']
    assert not result['training_executed'] and result['api_calls'] == 0


def test_future_registry_contents_cannot_create_known_candidates_or_new_name_spans(definition,evidence):
    original = bundle_for(definition,evidence)
    expanded = deepcopy(definition)
    expanded['assets'].append({'asset_id':'test:ONE','ticker':'ONE','aliases':[
        {'surface':'ONE','kind':'ticker','capture_sha256':'a'*64}]})
    future = bundle_for(expanded,evidence,registered='2000-01-02T00:00:00+00:00')
    past_original = assets.resolve_snapshot(snapshot(),original,decision_time=BEFORE,ttl_seconds=600)
    past_future = assets.resolve_snapshot(snapshot(),future,decision_time=BEFORE,ttl_seconds=600)
    assert past_original['mentions'] == past_future['mentions']
    assert past_original['candidate_state_sha256'] == past_future['candidate_state_sha256']
    assert all(r['lookup']['status'] == 'unknown' for r in past_original['mentions'])


def test_empty_or_expired_source_never_means_negative_asset_label(bundle):
    result = assets.resolve_snapshot(snapshot(),bundle,decision_time=REGISTERED,ttl_seconds=1)
    assert result['mentions'] == []
    assert not result['empty_result_is_negative_label'] and not result['source_coverage_verified']


def test_too_many_mentions_fail_without_partial_output_or_truncation(bundle):
    snap = snapshot()
    row = {k:snap['observations'][0][k] for k in snapshots.ROW_FIELDS}
    row['original_text'] = 'UNKNOWNUSDT '*129
    large = snapshots.build_snapshot({'schema_version':'semantic-source-export-v1','origin':'synthetic',
        'partition':'development','observations':[row]},snap['source_policy'])
    with pytest.raises(ValueError,match='no truncation'):
        assets.resolve_snapshot(large,bundle,decision_time=REGISTERED,ttl_seconds=600)


def test_definition_order_deterministic_and_does_not_mutate_inputs(definition,evidence):
    before = deepcopy((definition,evidence))
    left = assets._compile(definition,evidence)
    other = deepcopy(definition); other['assets'].reverse()
    for row in other['assets']: row['aliases'].reverse()
    assert left == assets._compile(other,evidence)
    assert before == (definition,evidence)


@pytest.mark.parametrize('change', ['id_duplicate','asset_extra','bad_ticker','pair_conflict','ticker_conflict',
    'alias_duplicate','missing_span','substring_only','unknown_capture','unbounded_alias','bad_kind',
    'bad_evidence_hash','unused_evidence','evidence_extra','unknown_origin','too_many_assets'])
def test_invalid_or_unproved_registry_cannot_be_compiled(definition,evidence,change):
    row = definition['assets'][0]; alias = row['aliases'][0]
    if change == 'id_duplicate': definition['assets'][1]['asset_id'] = row['asset_id']
    elif change == 'asset_extra': row['live_trading'] = True
    elif change == 'bad_ticker': row['ticker'] = 'aaa'
    elif change == 'pair_conflict': row['aliases'][1]['surface'] = 'BBBUSDT'
    elif change == 'ticker_conflict': alias['surface'] = 'BBB'
    elif change == 'alias_duplicate': row['aliases'].append(deepcopy(alias))
    elif change == 'missing_span': row['aliases'][2]['surface'] = 'Absent Project Name'
    elif change == 'substring_only': evidence[0]['original_text'] = TEXT.replace('AAA AAAUSDT','XAAA AAAUSDT')
    elif change == 'unknown_capture': alias['capture_sha256'] = 'f'*64
    elif change == 'unbounded_alias': row['aliases'][2]['surface'] = 'x'*121
    elif change == 'bad_kind': alias['kind'] = ['ticker']
    elif change == 'bad_evidence_hash': evidence[0]['raw_sha256'] = 'a'*12
    elif change == 'unused_evidence': evidence.append({**evidence[0],'raw_sha256':'f'*64})
    elif change == 'evidence_extra': evidence[0]['future_return'] = 0.1
    elif change == 'unknown_origin': definition['origin'] = 'human_gold'
    else: definition['assets'] *= 65
    with pytest.raises(ValueError): assets._compile(definition,evidence)


@pytest.mark.parametrize('change', ['alias','span','registration','implementation','missing_commit','future_capture'])
def test_tampered_bundle_refused_before_lookup(bundle,change):
    if change == 'alias': bundle['registry']['aliases'][0]['surface'] = 'FORGED'
    elif change == 'span': bundle['registry']['aliases'][0]['proof']['start'] += 1
    elif change == 'registration': bundle['registration']['registered_at'] = T0
    elif change == 'implementation': bundle['registry']['implementation']['asset_registry'] = 'f'*64
    elif change == 'missing_commit': bundle['registration'] = {}
    else: bundle['registry']['source_evidence'][0]['source_recorded_at'] = '2001-01-01T00:00:00Z'
    with pytest.raises(ValueError): assets.lookup(bundle,surface='AAA',kind='ticker',decision_time=REGISTERED)


def test_real_capture_freeze_cli_is_offline_private_and_not_overwritten(tmp_path,monkeypatch,definition):
    # This fixture mimics a capture locally; it asserts no actual remote observation.
    policy = {'schema_version':'semantic-source-policy-v1','policy_version':'test-v1',
              'sources':{'bybit-announcements':{'allowed_hosts':['announcements.bybit.com']}}}
    raw = ('<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'articleDetail':{
        'title':'SYNTHETIC assets','date':T0,'content':{'json':{'text':TEXT}}}}}})+'</script>').encode()
    sha = __import__('hashlib').sha256(raw).hexdigest()
    for asset in definition['assets']:
        for alias in asset['aliases']: alias['capture_sha256'] = sha
    monkeypatch.setattr(collector.transport,'fetch',lambda url:raw)
    times = iter([T0,T1,T2]); monkeypatch.setattr(collector,'_now',lambda:next(times))
    capture = tmp_path/'capture'
    collector.capture(capture,url='https://announcements.bybit.com/en/article/synthetic-assets/',policy=policy)
    def forbidden(*args,**kwargs): raise AssertionError('network/process execution forbidden')
    monkeypatch.setattr(socket,'socket',forbidden); monkeypatch.setattr(subprocess,'Popen',forbidden)
    definition_path = tmp_path/'definition.json'; definition_path.write_text(json.dumps(definition))
    directory = tmp_path/'registry'
    actual_datetime,actual_sync = assets.datetime,collector._sync
    synced = []
    def sync(path): synced.append(Path(path)); actual_sync(path)
    class Clock:
        @staticmethod
        def now(zone):
            assert (directory/'registry.json').is_file() and synced[-1] == directory
            return actual_datetime.now(zone)
    monkeypatch.setattr(collector,'_sync',sync); monkeypatch.setattr(assets,'datetime',Clock)
    argv = ['freeze','--definition',str(definition_path),'--capture',str(capture),'--directory',str(directory)]
    assert assets.main(argv) == 0
    bundle = assets.read_registry(directory)
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir())
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    output = tmp_path/'lookup.json'
    assert assets.main(['lookup','--registry',str(directory),'--surface','AAAUSDT','--kind','pair',
        '--decision-time',bundle['registration']['registered_at'],'--output',str(output)]) == 0
    assert json.loads(output.read_text())['status'] == 'unique_alias'
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): assets.main(argv)
    assert {p.name:p.read_bytes() for p in directory.iterdir()} == before


def test_partial_registry_without_registration_is_not_usable(tmp_path):
    directory = tmp_path/'partial'; directory.mkdir(); (directory/'registry.json').write_text('{}')
    with pytest.raises(FileNotFoundError): assets.read_registry(directory)
