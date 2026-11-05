from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from cryptoforge import source_review_package as review, semantic_asset_registry as assets
from cryptoforge import semantic_source_snapshot as snapshots, semantic_source_collector as collector
from cryptoforge.training_diagnostics import canonical, digest
from test_semantic_event_review import inputs, packet_for, TEXT


def entry(index=0, *, text=None, capture=None, url=None, item=None, cluster=None, event='withdrawal_halt', surface='AAAUSDT'):
    text = TEXT + ' CASE-' + str(index) if text is None else text
    snapshot, bundle = inputs(text)
    url = url or 'https://announcements.bybit.com/en/article/synthetic-review-' + str(index) + '/'
    capture = capture or digest({'synthetic_capture': index, 'text': text})
    definition = deepcopy(bundle['registry']['definition'])
    for asset in definition['assets']:
        for alias in asset['aliases']: alias['capture_sha256'] = capture
    evidence = deepcopy(bundle['registry']['source_evidence'])
    evidence[0].update(raw_sha256=capture, source_url=url)
    registry = assets._compile(definition, evidence)
    registration = {k: v for k, v in bundle['registration'].items() if k != 'registration_sha256'}
    registration['registry_sha256'] = registry['registry_sha256']
    bundle = {'registry': registry, 'registration': collector._seal(registration, 'registration_sha256')}
    rows = [{k: row[k] for k in snapshots.ROW_FIELDS} for row in snapshot['observations']]
    rows[0].update(source_url=url, capture_sha256=capture, source_item_id=item or 'synthetic-' + str(index))
    snapshot = snapshots.build_snapshot({'schema_version': 'semantic-source-export-v1', 'origin': 'synthetic',
        'partition': 'development', 'observations': rows}, snapshot['source_policy'])
    packet = packet_for(snapshot, bundle, surface=surface, event_type=event)
    return {'snapshot': snapshot, 'registry_bundle': bundle, 'packet': packet, 'declared_event_group': cluster}


def package_for(entries=None, **kwargs):
    return review.make_package([entry()] if entries is None else entries, seed=19,
        sample_groups=kwargs.pop('sample_groups', 1), holdout_groups=kwargs.pop('holdout_groups', 0),
        frame_kind=kwargs.pop('frame_kind', 'engineering_examples'), **kwargs)


def filled(package, reviewer='fixture-a', *, partition='calibration', kind='synthetic_fixture'):
    response = review.blank_response(package, partition=partition)
    response.update(reviewer_id=reviewer, review_kind=kind, reviewed_at='2026-10-19T05:00:00+00:00')
    response['attestation'] = {key: kind == 'human_review' for key in response['attestation']}
    for row in response['reviews']:
        for decision in row['decisions'].values():
            decision.update(status='answered', value='unknown', reason='Synthetic interface fixture; no actual annotation.')
    return response


def test_same_page_different_assets_events_and_knowledge_times_never_form_holdout():
    a = entry(); snapshot, bundle = a['snapshot'], a['registry_bundle']
    entries = []
    for surface in ('AAAUSDT', 'BBBUSDT'):
        for event in ('withdrawal_halt', 'trading_halt'):
            entries.append({**deepcopy(a), 'packet': packet_for(snapshot, bundle, surface=surface, event_type=event)})
    entries.append({**deepcopy(a), 'packet': packet_for(snapshot, bundle, decision_time='2000-01-01T00:00:00+00:00')})
    package = package_for(entries)
    assert package['frame_group_count'] == 1 and package['sampled_task_count'] == 5
    assert not package['minimum_split_group_count_met'] and not package['statistical_benchmark_qualified']
    assert package['partitions']['annotation_holdout'] == []
    with pytest.raises(ValueError): package_for(entries, sample_groups=2, holdout_groups=1)
    with pytest.raises(ValueError): review.blind_view(package, partition='annotation_holdout')


@pytest.mark.parametrize('basis', ['content', 'capture', 'url', 'document'])
def test_exact_and_provenance_links_merge_groups_even_with_different_declared_clusters(basis):
    first = entry(0, cluster='separate-a'); kwargs = {'cluster': 'separate-b'}
    if basis == 'content': kwargs['text'] = first['packet']['model_state']['source']['original_text']
    elif basis == 'capture': kwargs['capture'] = first['snapshot']['observations'][0]['capture_sha256']
    elif basis == 'url': kwargs['url'] = first['snapshot']['observations'][0]['source_url']
    else: kwargs['item'] = first['snapshot']['observations'][0]['source_item_id']
    package = package_for([first, entry(1, **kwargs)])
    assert package['frame_group_count'] == 1
    assert len({row['group_id'] for row in package['tasks']}) == 1


def test_related_group_links_are_transitive_and_only_merge():
    entries = [entry(0, cluster='story'), entry(1, cluster='story'), entry(2, item='synthetic-1')]
    assert package_for(entries)['frame_group_count'] == 1
    renamed = deepcopy(entries)
    for row in renamed:
        if row['declared_event_group']: row['declared_event_group'] = 'renamed-story'
    a, b = package_for(entries), package_for(renamed)
    assert a['package_sha256'] != b['package_sha256']
    assert a['tasks'] == b['tasks'] and a['partitions'] == b['partitions']


def test_sampling_and_partitions_are_deterministic_group_based_and_input_order_independent():
    entries = [entry(i) for i in range(4)]; original = deepcopy(entries)
    package = package_for(entries, sample_groups=3, holdout_groups=1, frame_kind='declared_population')
    reversed_package = package_for(list(reversed(entries)), sample_groups=3, holdout_groups=1, frame_kind='declared_population')
    assert package == reversed_package and entries == original
    assert package['frame_group_count'] == 4 and package['sampled_group_count'] == 3
    assert package['minimum_split_group_count_met']
    left, right = (set(package['partitions'][name]) for name in review.PARTITIONS)
    assert not left & right and len(left) == 2 and len(right) == 1
    groups = {row['task_id']: row['group_id'] for row in package['tasks']}
    assert not {groups[key] for key in left} & {groups[key] for key in right}
    assert not package['sampling_preregistered'] and not package['source_coverage_verified']
    assert not package['semantic_groups_audited'] and not package['statistical_benchmark_qualified']


def test_duplicate_and_confidence_only_task_variants_cannot_multiply_sampling_units():
    first = entry(); second = deepcopy(first)
    second['packet'] = packet_for(second['snapshot'], second['registry_bundle'], minimum_confidence=0.95)
    for rows in ([first, deepcopy(first)], [first, second]):
        with pytest.raises(ValueError, match='duplicate source task'): package_for(rows)


def test_future_audit_observation_does_not_merge_groups_or_leak_into_review_forms():
    first, second = entry(0), entry(1)
    original = package_for([first, second], sample_groups=2, holdout_groups=1)
    rows = [{key: row[key] for key in snapshots.ROW_FIELDS} for row in first['snapshot']['observations']]
    future = {key: second['snapshot']['observations'][0][key] for key in snapshots.ROW_FIELDS}
    for key in ('first_seen_at', 'received_at', 'recorded_at'): future[key] = '2000-01-02T00:00:00+00:00'
    rows.append(future)
    first['snapshot'] = snapshots.build_snapshot({'schema_version': 'semantic-source-export-v1',
        'origin': 'synthetic', 'partition': 'development', 'observations': rows}, first['snapshot']['source_policy'])
    first['packet'] = packet_for(first['snapshot'], first['registry_bundle'])
    changed = package_for([first, second], sample_groups=2, holdout_groups=1)
    assert changed['frame_group_count'] == 2 and changed['partitions'] == original['partitions']
    assert changed['package_sha256'] != original['package_sha256']
    for partition in review.PARTITIONS:
        assert review.blind_view(changed, partition=partition)['tasks'] == review.blind_view(original, partition=partition)['tasks']


@pytest.mark.parametrize('kwargs', [
    {'seed': True}, {'seed': -1}, {'seed': 2**32}, {'sample_groups': True},
    {'sample_groups': 0}, {'sample_groups': 2}, {'holdout_groups': True},
    {'holdout_groups': -1}, {'holdout_groups': 1}, {'frame_kind': 'random_entire_feed'},
])
def test_sampling_policy_is_explicit_and_bounded(kwargs):
    args = dict(seed=19, sample_groups=1, holdout_groups=0, frame_kind='engineering_examples'); args.update(kwargs)
    with pytest.raises(ValueError): review.make_package([entry()], **args)


@pytest.mark.parametrize('mutation', ['partition', 'group', 'qualification', 'source', 'extra'])
def test_forged_or_resealed_package_and_split_are_rejected(mutation):
    package = package_for([entry(0), entry(1)], sample_groups=2, holdout_groups=1)
    if mutation == 'partition': package['partitions']['calibration'] += package['partitions']['annotation_holdout']
    elif mutation == 'group': package['tasks'][0]['group_id'] = 'f' * 64
    elif mutation == 'qualification': package['statistical_benchmark_qualified'] = True
    elif mutation == 'source': package['entries'][0]['snapshot']['observations'][0]['original_text'] += ' forged'
    else: package['prediction'] = {'choice': 'fake'}
    package['package_sha256'] = digest({k: v for k, v in package.items() if k != 'package_sha256'})
    with pytest.raises(ValueError): review.validate_package(package)


def test_blind_view_excludes_other_partitions_labels_and_confidence_policy():
    package = package_for([entry(0), entry(1)], sample_groups=2, holdout_groups=1)
    view = review.blind_view(package, partition='calibration')
    assert {row['task_id'] for row in view['tasks']} == set(package['partitions']['calibration'])
    assert 'minimum_confidence' not in canonical(view) and 'probabilities' not in canonical(view)
    assert not view['contains_model_answers'] and not view['contains_gold_labels']
    for row in view['tasks']:
        assert set(row['questions']) == {'asset', 'source_support', 'message_kind', 'market_scope', 'event_state', 'evidence'}
        assert row['source_origin'] == row['registry_origin'] == 'synthetic'
        assert row['state']['source']['original_text']
    response = review.blank_response(package, partition='calibration')
    assert response['reviewer_id'] is None and not any(response['attestation'].values())
    for row in response['reviews']:
        assert all(value == {'status': 'pending', 'value': None, 'reason': None} for value in row['decisions'].values())
    with pytest.raises(ValueError): review.complete_review(package, response, partition='calibration')


def test_complete_fixture_and_human_declaration_remain_unverified():
    package = package_for()
    for kind in ('synthetic_fixture', 'human_review'):
        response = filled(package, kind=kind)
        before = deepcopy(response)
        imported = review.complete_review(package, response, partition='calibration')
        assert response == before and imported['review_kind'] == kind
        assert imported['authorship_assurance'] == 'reviewer_declaration_only_not_authenticated'
        for flag in ('human_gold_verified', 'semantic_groups_audited', 'training_labels_created', 'historical_feature_availability_verified'):
            assert imported[flag] is False


@pytest.mark.parametrize('mutation', ['human_missing', 'synthetic_claim', 'integer_attestation', 'pending', 'invalid_choice',
    'missing_question', 'wrong_state', 'wrong_rubric', 'wrong_view', 'extra_field', 'empty_reason', 'invalid_time'])
def test_incomplete_or_unbound_review_cannot_be_imported(mutation):
    package = package_for(); response = filled(package)
    row = response['reviews'][0]
    if mutation == 'human_missing': response['review_kind'] = 'human_review'
    elif mutation == 'synthetic_claim': response['attestation']['human_authored'] = True
    elif mutation == 'integer_attestation': response['attestation']['human_authored'] = 0
    elif mutation == 'pending': row['decisions']['asset']['status'] = 'pending'
    elif mutation == 'invalid_choice': row['decisions']['evidence']['value'] = 'invented_quote'
    elif mutation == 'missing_question': row['decisions'].pop('event_state')
    elif mutation == 'wrong_state': row['state_sha256'] = 'f' * 64
    elif mutation == 'wrong_rubric': row['rubric_sha256'] = 'f' * 64
    elif mutation == 'wrong_view': response['view_sha256'] = 'f' * 64
    elif mutation == 'extra_field': response['model_answers'] = {}
    elif mutation == 'empty_reason': row['decisions']['asset']['reason'] = ' '
    else: response['reviewed_at'] = '2026-10-19'
    with pytest.raises(ValueError): review.complete_review(package, response, partition='calibration')


def test_null_insufficient_unknown_and_no_match_stay_distinct():
    package = package_for(); response = filled(package)
    decisions = response['reviews'][0]['decisions']
    decisions['asset']['value'] = 'no_match'
    decisions['event_state'].update(status='insufficient', value=None)
    result = review.complete_review(package, response, partition='calibration')
    values = result['reviews'][0]['decisions']
    assert values['asset']['value'] == 'no_match' and values['message_kind']['value'] == 'unknown'
    assert values['event_state']['status'] == 'insufficient' and values['event_state']['value'] is None
    decisions['event_state']['value'] = 'not_stated'
    with pytest.raises(ValueError): review.complete_review(package, response, partition='calibration')


def test_reviews_cannot_cross_partitions_or_omit_or_repeat_tasks():
    package = package_for([entry(0), entry(1), entry(2)], sample_groups=3, holdout_groups=1)
    response = filled(package)
    with pytest.raises(ValueError): review.complete_review(package, response, partition='annotation_holdout')
    for rows in (response['reviews'][:-1], [response['reviews'][0], response['reviews'][0]]):
        changed = {**response, 'reviews': rows}
        with pytest.raises(ValueError): review.complete_review(package, changed, partition='calibration')


def test_two_reviewer_comparison_preserves_disputes_and_insufficient_cases():
    first = entry(); second = {**deepcopy(first), 'packet': packet_for(first['snapshot'], first['registry_bundle'], surface='BBBUSDT')}
    package = package_for([first, second]); a, b = filled(package, 'fixture-a'), filled(package, 'fixture-b')
    b['reviews'][0]['decisions']['asset']['value'] = 'no_match'
    for raw in (a, b): raw['reviews'][0]['decisions']['evidence'].update(status='insufficient', value=None)
    a['reviews'][1]['decisions']['source_support'].update(status='insufficient', value=None)
    result = review.compare_reviews(package, a, b, partition='calibration')
    asset = result['questions']['asset']
    assert asset == {'both_answered_count': 2, 'agreed_answer_count': 1, 'joint_insufficient_count': 0,
                     'disputed_count': 1, 'agreement_on_answered': 0.5}
    assert result['questions']['evidence']['joint_insufficient_count'] == 1
    assert result['questions']['source_support']['disputed_count'] == 1
    assert result['outcomes'][0]['decisions']['asset']['value'] is None
    assert result['outcomes'][0]['decisions']['evidence']['status'] == 'joint_insufficient'
    for flag in ('reviewer_independence_authenticated', 'disagreements_adjudicated', 'human_gold_verified',
                 'semantic_groups_audited', 'statistical_benchmark_qualified', 'model_quality_evaluated', 'training_labels_created'):
        assert result[flag] is False
    assert result['review_kind'] == 'synthetic_fixture' and result['api_calls'] == 0


def test_both_insufficient_has_null_answered_agreement_and_is_not_a_label():
    package = package_for(); a, b = filled(package, 'fixture-a'), filled(package, 'fixture-b')
    for raw in (a, b):
        for decision in raw['reviews'][0]['decisions'].values(): decision.update(status='insufficient', value=None)
    result = review.compare_reviews(package, a, b, partition='calibration')
    for metric in result['questions'].values():
        assert metric['agreement_on_answered'] is None and metric['joint_insufficient_count'] == 1


def test_same_reviewer_and_mixed_origins_cannot_claim_two_independent_reviews():
    package = package_for(); a = filled(package)
    with pytest.raises(ValueError): review.compare_reviews(package, a, deepcopy(a), partition='calibration')
    b = filled(package, 'fixture-b', kind='human_review')
    with pytest.raises(ValueError): review.compare_reviews(package, a, b, partition='calibration')


def write_inputs(tmp_path, entries):
    manifest = []
    for i, item in enumerate(entries):
        directory = tmp_path/str(i); directory.mkdir()
        for name in ('snapshot', 'packet'): (directory/(name+'.json')).write_text(canonical(item[name]))
        registry = directory/'registry'; registry.mkdir()
        for name, value in item['registry_bundle'].items(): (registry/(name+'.json')).write_text(canonical(value))
        manifest.append({'snapshot': str(i)+'/snapshot.json', 'packet': str(i)+'/packet.json',
                         'registry': str(i)+'/registry', 'declared_event_group': item['declared_event_group']})
    path = tmp_path/'manifest.json'; path.write_text(canonical(manifest)); return path


def test_offline_cli_private_forms_complete_compare_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('offline review must not use network'))
    manifest = write_inputs(tmp_path, [entry()]); directory = tmp_path/'package'
    args = ['prepare', '--manifest', str(manifest), '--seed', '19', '--sample-groups', '1',
        '--holdout-groups', '0', '--frame-kind', 'engineering_examples', '--directory', str(directory)]
    assert review.main(args) == 0
    with pytest.raises(FileExistsError): review.main(args)
    package_path = directory/'package.json'; package = json.loads(package_path.read_text())
    forms = tmp_path/'forms'
    assert review.main(['forms', '--package', str(package_path), '--partition', 'calibration', '--directory', str(forms)]) == 0
    for name, reviewer in (('response-a', 'fixture-a'), ('response-b', 'fixture-b')):
        (forms/(name+'.json')).write_text(canonical(filled(package, reviewer)))
    common = ['--package', str(package_path), '--partition', 'calibration']
    complete = tmp_path/'complete.json'
    assert review.main(['complete', *common, '--response', str(forms/'response-a.json'), '--output', str(complete)]) == 0
    compare = tmp_path/'compare.json'
    assert review.main(['compare', *common, '--response-a', str(forms/'response-a.json'),
                        '--response-b', str(forms/'response-b.json'), '--output', str(compare)]) == 0
    for path in (package_path, forms/'blind-view.json', complete, compare): assert path.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == forms.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError): review.main(['complete', *common, '--response', str(forms/'response-a.json'), '--output', str(complete)])
    with pytest.raises(ValueError): review.main(['forms', '--package', str(package_path), '--partition', 'annotation_holdout', '--directory', str(tmp_path/'empty')])
    assert not (tmp_path/'empty').exists()


def test_input_count_and_response_bytes_are_bounded_before_use(tmp_path):
    for entries in ([], [{}] * 65):
        with pytest.raises(ValueError): package_for(entries)
    package = package_for(); raw = filled(package); raw['padding'] = 'x' * review.MAX_RESPONSE_BYTES
    with pytest.raises(ValueError, match='bounded reviewer'): review.complete_review(package, raw, partition='calibration')
    manifest = tmp_path/'manifest.json'; manifest.write_text(canonical([{}] * 65))
    with pytest.raises(ValueError, match='manifest entries'):
        review.main(['prepare', '--manifest', str(manifest), '--seed', '19', '--sample-groups', '1',
            '--holdout-groups', '0', '--frame-kind', 'engineering_examples', '--directory', str(tmp_path/'out')])
    assert not (tmp_path/'out').exists()
