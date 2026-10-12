from copy import deepcopy
from datetime import UTC,datetime,timedelta
import hashlib
import json
from pathlib import Path
import pytest

from cryptoforge.live_learning_protocol import evaluate_readiness,load_protocol,buy_key,SPLITS

BASE=Path('config/live-cash-recovery-protocol-v1.json')
START=datetime(2026,1,1,tzinfo=UTC)


def protocol():
    p=json.loads(BASE.read_bytes());p['frozen_at']=START.isoformat();p['development_buy_keys']=[]
    for split,a,b in zip(SPLITS,(0,28,42,70),(28,42,70,98)):
        p['windows'][split]={'start':(START+timedelta(days=a)).isoformat(),'end_exclusive':(START+timedelta(days=b)).isoformat()}
        p['minimums'][split]={'buy_orders':2,'entry_days':1,'pairs':1}
        if split in {'train','validation'}:p['minimums'][split].update(positive=1,negative=1)
    p['maximum_pair_fraction']='1';p['maximum_entry_day_fraction']='1'
    return p


def row(identity,day,*,label=0,known_day=None,state='legacy_asof_snapshot'):
    entry=START+timedelta(days=day,hours=1)
    closed=entry+timedelta(hours=1)
    available=START+timedelta(days=known_day,hours=4) if known_day is not None else closed+timedelta(hours=1)
    return {'pair':'AAA/USDT','entry_order':identity,'entry_at':entry.isoformat(),'closed_at':closed.isoformat(),
        'target_version':'spot-long-real-cash-recovery-dust-zero-v1','feature_version':'candle-v1',
        'input_candle_state':state,'label_available_at':available.isoformat(),
        'example':{'pair':'AAA/USDT','open_time':(entry-timedelta(seconds=1)).isoformat(),
                   'features':[0,0,.01,1,0,.5,0],'label':label}}


def ready_rows():
    return {'train':[row('t1',2,label=0),row('t2',3,label=1)],
            'validation':[row('v1',30,label=0),row('v2',31,label=1)],
            'sealed_test':[row('s1',44,label=0),row('s2',45,label=1)]}


def test_frozen_protocol_checksum_cannot_silently_change_thresholds(tmp_path):
    path=tmp_path/'protocol.json';raw=BASE.read_bytes();path.write_bytes(raw)
    path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    assert load_protocol(path)['minimums']['train']['buy_orders']==100
    path.write_bytes(raw.replace(b'100',b'101',1))
    with pytest.raises(ValueError,match='checksum'):load_protocol(path)


def test_adequate_train_validation_only_ready_after_windows_finish():
    p=protocol();rows=ready_rows()
    early=evaluate_readiness(p,rows,as_of=START+timedelta(days=40),source_healthy=True)
    assert not early['data_ready_for_offline_fit']
    after=evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)
    assert after['data_ready_for_offline_fit'] and not after['sealed_test_data_ready']
    assert after['live_promotion_allowed'] is False


def test_explicit_future_window_contract_cannot_be_filled_from_unknown_or_other_windows():
    p=protocol();rows=ready_rows()
    contract={'feature_version':'candle-v1','timeframe':'5m','input_candle_state':p['input_candle_state'],
        'calculation_contract':'bounded-window-candle-v1','lookback_candles':120}
    p['feature_input_contract']=contract
    result=evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)
    assert not result['data_ready_for_offline_fit']
    assert result['splits']['train']['excluded']['incompatible_feature_calculation_contract']==2
    for values in rows.values():
        for value in values:value['feature_input_contract']=deepcopy(contract)
    assert evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)['data_ready_for_offline_fit']
    rows['train'][0]['feature_input_contract']['lookback_candles']=36
    assert not evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)['data_ready_for_offline_fit']


@pytest.mark.parametrize('field,value',[('embargo_seconds',-1),('embargo_seconds',True),
    ('minimum_example_snapshot_freshness_seconds',0),('automatic_training_allowed',None),
    ('live_promotion_allowed',0),('market','bybit_futures')])
def test_invalid_collection_safeguards_are_not_accepted_as_frozen_policy(field,value):
    from cryptoforge.live_learning_protocol import validate_protocol
    p=protocol();p[field]=value
    with pytest.raises(ValueError):validate_protocol(p)


def test_fractional_sample_minimum_and_unhashed_known_buys_do_not_qualify():
    from cryptoforge.live_learning_protocol import validate_protocol
    p=protocol();p['minimums']['train']['buy_orders']=1.5
    with pytest.raises(ValueError,match='integer'):validate_protocol(p)
    p=protocol();p['development_buy_keys']=['fake-order']
    with pytest.raises(ValueError,match='hashes'):validate_protocol(p)


def test_test_labels_never_influence_readiness_or_get_reported():
    p=protocol();rows=ready_rows();now=START+timedelta(days=71)
    before=evaluate_readiness(p,rows,as_of=now,source_healthy=True)
    for r in rows['sealed_test']:r['example']['label']=1-r['example']['label']
    after=evaluate_readiness(p,rows,as_of=now,source_healthy=True)
    assert before['splits']['sealed_test']==after['splits']['sealed_test']
    assert 'positive' not in after['splits']['sealed_test']['counts']


def test_development_identity_cannot_be_moved_to_validation_by_correction():
    p=protocol();known=row('known',-2,label=1,known_day=1);p['development_buy_keys']=[buy_key(known)]
    corrected=row('known',30,label=1)
    result=evaluate_readiness(p,{'train':[known],'validation':[corrected]},
        as_of=START+timedelta(days=43),source_healthy=True)
    assert result['splits']['train']['counts']['buy_orders']==1
    assert result['splits']['validation']['counts']['buy_orders']==0
    assert result['splits']['validation']['excluded']['development_buy_not_independent']==1


def test_late_label_and_boundary_entry_are_purged():
    p=protocol();rows={'train':[row('late',25,known_day=28)],'validation':[row('boundary',28)]}
    result=evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)
    assert result['splits']['train']['counts']['buy_orders']==0
    assert result['splits']['validation']['counts']['buy_orders']==0


def test_multiple_versions_or_candle_contracts_cannot_be_mixed():
    p=protocol();sample=row('same',2)
    with pytest.raises(ValueError,match='duplicate'):
        evaluate_readiness(p,{'train':[sample,deepcopy(sample)]},as_of=START+timedelta(days=43),source_healthy=True)
    changed=row('closed',3,state='closed_only')
    result=evaluate_readiness(p,{'train':[changed]},as_of=START+timedelta(days=43),source_healthy=True)
    assert result['splits']['train']['excluded']['incompatible_candle_input_state']==1


def test_same_buy_changed_entry_time_cannot_span_two_folds():
    p=protocol();rows={'train':[row('same',2)],'validation':[row('same',30)]}
    result=evaluate_readiness(p,rows,as_of=START+timedelta(days=43),source_healthy=True)
    assert result['cross_split_buy_conflicts']==1
    assert 'buy_identity_crosses_split_boundaries' in result['blocked_reasons']


def test_counts_do_not_override_single_day_or_pair_concentration():
    p=protocol();p['maximum_entry_day_fraction']='.25';p['maximum_pair_fraction']='.35'
    result=evaluate_readiness(p,ready_rows(),as_of=START+timedelta(days=43),source_healthy=True)
    assert not result['data_ready_for_offline_fit']
    assert 'pair_concentration' in [r['gate'] for r in result['splits']['train']['failures']]


def test_live_bot_outcomes_do_not_count_as_candidate_paper_execution():
    p=protocol();rows={'paper':[row('live1',72),row('live2',73)]}
    result=evaluate_readiness(p,rows,as_of=START+timedelta(days=99),source_healthy=True)
    assert result['splits']['paper']['counts']['buy_orders']==0
    assert result['splits']['paper']['excluded']['candidate_paper_execution_evidence_required']==2
    assert not result['paper_harness_implemented']


def test_stale_or_unverified_collection_blocks_fit():
    result=evaluate_readiness(protocol(),ready_rows(),as_of=START+timedelta(days=43),source_healthy=False)
    assert not result['data_ready_for_offline_fit']
    assert result['blocked_reasons']==['unverified_stale_or_incomplete_collection_snapshot']


def test_collection_freshness_cannot_hide_truncation_or_missing_pair_observations():
    from cryptoforge.live_learning_protocol import collection_is_healthy
    p=protocol();now=START+timedelta(days=1)
    healthy={'snapshot_observed_at':now.isoformat(),'accounting_quality_verified':True,
             'source_binding_verified':True,'source_binding_mismatches':0,
             'snapshot_truncated':False,'observation_errors':{},
             'observation_scope':{'eligible_pair_count':4,'maximum_pairs':20}}
    assert collection_is_healthy(healthy,p,now)
    assert not collection_is_healthy({**healthy,'snapshot_truncated':True},p,now)
    assert not collection_is_healthy({**healthy,'source_binding_mismatches':1},p,now)
    assert not collection_is_healthy({**healthy,'observation_errors':{'A':'timeout'}},p,now)
    assert not collection_is_healthy({**healthy,'observation_scope':{'eligible_pair_count':21,'maximum_pairs':20}},p,now)
    assert not collection_is_healthy(healthy,p,now+timedelta(hours=1))


def test_unexplained_collection_omissions_block_readiness_health():
    from cryptoforge.live_learning_protocol import collection_is_healthy
    p=protocol();now=START+timedelta(days=42)
    current={'snapshot_observed_at':now.isoformat(),'accounting_quality_verified':True,
             'source_binding_verified':True,'observation_scope':{'eligible_pair_count':1,'observed_pair_count':1}}
    assert collection_is_healthy(current,p,now)
    current['collection_coverage']={'unexplained_omissions':1}
    assert not collection_is_healthy(current,p,now)


def test_collection_reports_contracts_separately_without_inflating_buys():
    from cryptoforge.live_learning_protocol import collection_contract_counts
    rows=[row('legacy',2),row('closed',3,state='closed_only')]
    result=collection_contract_counts(rows)
    assert result['by_input_candle_state']=={'legacy_asof_snapshot':1,'closed_only':1}
    assert not result['different_contracts_mixed_for_training']
    with pytest.raises(ValueError,match='duplicate'):collection_contract_counts(rows+[rows[0]])
