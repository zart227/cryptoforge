"""Counterfactual source diagnostics; no data refresh, model or provider calls."""
from copy import deepcopy
import pytest
from cryptoforge import research_source_remediation as m


def case():
    names=m.dataset.source.POLICY['pairs']; rows=[]
    for i,name in enumerate(names):
        stale=i>=13
        rows.append({'pair':name,'expected_native_exclusion':'stale closed training source' if stale else None,
            'latest_known_closed_at':'2026-10-26T11:45:00+00:00',
            'latest_known_closed_age_microseconds':1_419_379_786 if stale else 219_379_786,
            'known_closed_gap_count':0})
    coverage={'accepted_pairs':13,'requested_pairs':20,'minimum_satisfied':False}
    diag={'report_sha256':'d'*64,'capture_sha256':'c'*64,'coverage':coverage,
          'proposal_route':'review_source_data','source_blocking_reasons':['minimum_pair_coverage_not_met'],
          'diagnostic_as_of':'2026-10-26T12:08:39.379786+00:00','pairs':rows,
          'accepted_pairs':names[:13],'excluded_pairs':{n:'stale closed training source' for n in names[13:]}}
    review={'source_diagnostics_sha256':diag['report_sha256'],'binding':{'capture_sha256':diag['capture_sha256'],
        'diagnostics_directory':'synthetic'},'source_coverage':deepcopy(coverage),
        'source_proposal_route':diag['proposal_route'],'source_blocking_reasons':deepcopy(diag['source_blocking_reasons']),
        'training_admitted':False,'historical_first_seen_revision_lineage_verified':False,
        'provider_proposals_authorized':False,'review_sha256':'e'*64}
    return review,diag


def test_original_snapshot_timing_and_conditional_coverage_shortfall():
    review,diag=case(); result=m._derive(review,diag)
    assert (result['accepted_pair_count'],result['required_pair_count'])==(13,16)
    assert result['minimum_additional_accepted_pairs_if_existing_remain_accepted']==3
    assert result['first_fresh_close_for_original_cutoff']=='2026-10-26T11:55:00+00:00'
    assert len(result['excluded_pairs'])==7
    assert all(row['age_over_limit_microseconds']==519_379_786 for row in result['excluded_pairs'])
    assert result['snapshot_status_is_current'] is False
    assert result['historical_lineage_or_missing_candles_proven'] is False
    assert result['coverage_implies_training_or_provider_admission'] is False
    core={k:v for k,v in result.items() if k!='report_sha256'}
    assert result['report_sha256']==m.digest(core)


@pytest.mark.parametrize(('cutoff','expected'),[
    ('2026-10-26T12:10:00+00:00','2026-10-26T11:55:00+00:00'),
    ('2026-10-26T12:10:00.000001+00:00','2026-10-26T12:00:00+00:00'),
    ('2026-10-26T15:08:39.379786+03:00','2026-10-26T11:55:00+00:00'),
    ('1969-12-31T23:59:59+00:00','1969-12-31T23:45:00+00:00'),
])
def test_first_fresh_close_uses_ceiling_including_exact_and_negative_epoch(cutoff,expected):
    assert m._next_boundary(cutoff,900_000_000,300)==expected


@pytest.mark.parametrize('change',['review_digest','capture','coverage','route','training','lineage',
    'provider','pair_order','excluded','stale_age','boolean_age','gate'])
def test_mismatched_review_or_source_is_rejected(change):
    review,diag=case()
    if change=='review_digest':review['source_diagnostics_sha256']='x'*64
    elif change=='capture':review['binding']['capture_sha256']='x'*64
    elif change=='coverage':review['source_coverage']['accepted_pairs']=14
    elif change=='route':review['source_proposal_route']='review_research_protocol'
    elif change=='training':review['training_admitted']=True
    elif change=='lineage':review['historical_first_seen_revision_lineage_verified']=True
    elif change=='provider':review['provider_proposals_authorized']=True
    elif change=='pair_order':diag['pairs'].reverse()
    elif change=='excluded':diag['excluded_pairs'].pop(next(iter(diag['excluded_pairs'])))
    elif change=='stale_age':diag['pairs'][-1]['latest_known_closed_age_microseconds']=900_000_000
    elif change=='boolean_age':diag['pairs'][-1]['latest_known_closed_age_microseconds']=True
    else:diag['coverage']['minimum_satisfied']=True;review['source_coverage']['minimum_satisfied']=True
    with pytest.raises(ValueError):m._derive(review,diag)


def test_verified_entry_rechecks_review_and_source_without_worker_or_transport(monkeypatch):
    review,diag=case();calls=[]
    monkeypatch.setattr(m.dataset,'verify',lambda path:(calls.append(('review',path)) or deepcopy(review)))
    monkeypatch.setattr(m.dataset.source,'verify',lambda path:(calls.append(('diagnostics',path)) or deepcopy(diag)))
    monkeypatch.setattr(m.dataset.subprocess,'Popen',lambda *a,**k:pytest.fail('no worker'))
    result=m.analyze_verified('synthetic-review')
    assert calls==[('review','synthetic-review'),('diagnostics','synthetic')]
    assert result['database_network_provider_fit_prediction_actions']==0


def test_mutated_policy_fails_closed(monkeypatch):
    review,diag=case();monkeypatch.setitem(m.POLICY,'uses_original_review_only',False)
    with pytest.raises(ValueError,match='fixed_source_remediation_required'):m._derive(review,diag)
