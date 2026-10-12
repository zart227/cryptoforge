from copy import deepcopy
from datetime import UTC,datetime,timedelta
from pathlib import Path
import json,sqlite3
import pytest
from cryptoforge.prospective_shadow import ShadowLedger,LocalShadowObserver,validate_candidate,compare_factual_cohort
from cryptoforge.live_learning_protocol import load_protocol,time

PROTOCOL=load_protocol(Path('config/live-cash-recovery-protocol-v1.json'))
TEST_START=time(PROTOCOL['windows']['sealed_test']['start'])+timedelta(days=1)
TEST_END=time(PROTOCOL['windows']['sealed_test']['end_exclusive'])
FEATURES=[0.,0.,.01,1.,0.,.5,0.]


def candidate():
    selected=time(PROTOCOL['windows']['validation']['end_exclusive'])+timedelta(hours=1)
    manifest={'protocol_version':PROTOCOL['protocol_version'],'selected_at':selected.isoformat(),
              'threshold':'0.50','live_eligible':False}
    artifact={'model_family':'pure-python-logistic','selected_l2':.01,'feature_version':'candle-v1','trained_at':selected.isoformat(),
              'live_eligible':False,'threshold':.5,
              'feature_names':['return_1','return_3','range_12','volume_ratio','ema_gap','rsi_14','candle_body'],
              'weights':[0.]*7,'means':[0.]*7,'stds':[1.]*7,'bias':0.,
              'config':{'target_version':PROTOCOL['target_version'],'input_candle_state':'legacy_asof_snapshot',
                        'fit_information_end':(selected-timedelta(days=2)).isoformat()}}
    return manifest,artifact


def record(ledger,opportunity='o1',probability=.6,at=TEST_START):
    return ledger.record(candidate_sha='a'*64,opportunity=opportunity,pair='AAA/USDT',features=FEATURES,
        feature_observed_at=at-timedelta(seconds=1),input_state='legacy_asof_snapshot',
        probability=probability,threshold=.5,predicted_at=at)


def test_absent_candidate_is_inert_without_creating_ledger(tmp_path):
    observer=LocalShadowObserver(tmp_path/'absent.json',tmp_path/'ledger.sqlite')
    assert observer.before_buy(pair='AAA/USDT',opportunity='o',model_input=None,feature_observed_at=TEST_START) is None
    assert not (tmp_path/'ledger.sqlite').exists()


def test_invalid_configured_study_does_not_fail_executor_construction(monkeypatch,tmp_path):
    monkeypatch.setenv('CRYPTOFORGE_CASH_SHADOW_PROTOCOL',str(tmp_path/'missing.json'))
    observer=LocalShadowObserver.from_env()
    assert not (tmp_path/'missing.json').exists()
    with pytest.raises(OSError):
        observer.before_buy(pair='AAA/USDT',opportunity='o',model_input=None,feature_observed_at=TEST_START)


def test_prediction_preserves_original_window_contract_and_cannot_relabel_it(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START)
    kwargs=dict(candidate_sha='a'*64,opportunity='o1',pair='AAA/USDT',features=FEATURES,
        feature_observed_at=TEST_START-timedelta(seconds=1),input_state='legacy_asof_snapshot',
        probability=.6,threshold=.5,predicted_at=TEST_START)
    contract={'lookback_candles':120,'calculation_contract':'bounded-window-candle-v1'}
    ledger.record(**kwargs,feature_input_contract=contract)
    assert ledger.rows()[0]['feature_input_contract']==contract
    with pytest.raises(ValueError,match='overwrite'):
        ledger.record(**kwargs,feature_input_contract={**contract,'lookback_candles':36})


def test_prediction_is_durable_before_order_and_cannot_be_overwritten(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);assert record(ledger)
    assert ledger.rows()[0]['order_id'] is None
    assert record(ledger) is False
    with pytest.raises(ValueError,match='overwrite'):record(ledger,probability=.1)
    ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START+timedelta(seconds=1))
    assert ledger.rows()[0]['order_id']=='buy1'
    with pytest.raises(ValueError,match='rebind'):
        ledger.bind_order('a'*64,'o1','buy2',bound_at=TEST_START+timedelta(seconds=2))


def test_two_opportunities_cannot_duplicate_one_factual_order(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger);record(ledger,'o2')
    ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START+timedelta(seconds=1))
    with pytest.raises(sqlite3.IntegrityError):ledger.bind_order('a'*64,'o2','buy1',bound_at=TEST_START+timedelta(seconds=1))


def test_future_features_and_binding_before_prediction_are_rejected(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger)
    with pytest.raises(ValueError,match='prediction must exist'):
        ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START-timedelta(seconds=1))
    with pytest.raises(ValueError,match='known before prediction'):
        ledger.record(candidate_sha='a'*64,opportunity='o3',pair='AAA/USDT',features=FEATURES,
            feature_observed_at=TEST_START+timedelta(seconds=1),input_state='legacy_asof_snapshot',
            probability=.6,threshold=.5,predicted_at=TEST_START)


def test_candidate_freeze_and_information_end_must_precede_holdout():
    manifest,artifact=candidate();validate_candidate(manifest,artifact,PROTOCOL,now=TEST_START)
    late=deepcopy(manifest);late['selected_at']=(TEST_START+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='frozen before'):validate_candidate(late,artifact,PROTOCOL,now=TEST_START+timedelta(hours=1))
    artifact['config']['fit_information_end']=TEST_START.isoformat()
    with pytest.raises(ValueError,match='post-selection'):validate_candidate(manifest,artifact,PROTOCOL,now=TEST_START)


def outcomes():
    return [{'pair':'AAA/USDT','entry_order':order,'entry_at':(TEST_START+timedelta(seconds=1)).isoformat(),
             'label_available_at':(TEST_START+timedelta(hours=2)).isoformat(),
             'input_candle_state':'legacy_asof_snapshot','target_version':PROTOCOL['target_version'],
             'cash_recovery_net':pnl,'example':{'open_time':(TEST_START-timedelta(seconds=1)).isoformat(),
                                             'features':FEATURES}} for order,pnl in [('buy1','.1'),('buy2','-.2')]]


def test_sealed_period_reports_no_outcome_statistics(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger)
    report=compare_factual_cohort(ledger.rows(),outcomes(),PROTOCOL,candidate_sha='a'*64,
                                 split='sealed_test',as_of=TEST_START+timedelta(days=1))
    assert report['performance_hidden'] and 'baseline_factual_cash_recovery' not in report


def test_actual_cohort_is_not_simulated_portfolio_profit(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger);record(ledger,'o2',probability=.1)
    for op,order in [('o1','buy1'),('o2','buy2')]:
        ledger.bind_order('a'*64,op,order,bound_at=TEST_START+timedelta(seconds=1))
    report=compare_factual_cohort(ledger.rows(),outcomes(),PROTOCOL,candidate_sha='a'*64,split='sealed_test',as_of=TEST_END)
    assert report['baseline_factual_cash_recovery']=='-0.1'
    assert report['candidate_accepted_factual_cash_recovery']=='0.1'
    assert report['candidate_rejected_factual_cash_recovery']=='-0.2'
    assert not report['portfolio_income_claim_allowed'] and not report['live_promotion_allowed']


def test_prediction_recorded_after_entry_or_changed_features_is_not_prospective(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger)
    ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START+timedelta(seconds=1))
    rows=outcomes();rows[0]['entry_at']=(TEST_START-timedelta(seconds=1)).isoformat()
    report=compare_factual_cohort(ledger.rows(),rows,PROTOCOL,candidate_sha='a'*64,split='sealed_test',as_of=TEST_END)
    assert report['matched_factual_buys']==0


def test_candidate_selection_needs_observed_immutable_registration(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);manifest,_=candidate()
    manifest.update(artifact_sha256='a'*64,protocol_sha256='b'*64)
    raw=json.dumps(manifest,sort_keys=True).encode();selected=time(manifest['selected_at']);ledger.clock=lambda:selected
    with pytest.raises(ValueError,match='no observed registration'):ledger.verify_freeze(raw)
    ledger.freeze_candidate(raw,registered_at=selected)
    assert ledger.verify_freeze(raw)==selected
    changed={**manifest,'threshold':'0.75'}
    with pytest.raises(ValueError,match='not frozen or has changed'):
        ledger.verify_freeze(json.dumps(changed,sort_keys=True).encode())
    with pytest.raises(ValueError,match='actual selection time'):
        ledger.freeze_candidate(raw,registered_at=selected+timedelta(seconds=1))


def test_executor_observer_failure_does_not_block_order_recording(monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace
    from unittest.mock import Mock
    import cryptoforge.supabase_executor as module
    from test_supabase_executor import support_bounce_candles
    events=[];candles=support_bounce_candles()
    class Broken:
        def before_buy(self,**kwargs):events.append('before');raise RuntimeError('ledger unavailable')
        def after_buy(self,receipt,order):events.append('after')
    def buy(**kwargs):events.append('buy');return {'retCode':0,'result':{'orderId':'buy1'}}
    bybit=SimpleNamespace(get_open_orders=lambda **kwargs:[],get_unified_coin_wallet_balance=lambda coin:Decimal(0),
        get_spot_instrument=lambda symbol:SimpleNamespace(quantity_step=Decimal('.000001'),minimum_quantity=Decimal('.000001'),minimum_order_amount=Decimal('5')),
        get_unified_usdt_balance=lambda:SimpleNamespace(usdt_wallet_balance=Decimal(100)),create_spot_market_order=buy)
    cloud=Mock();cloud.upsert.side_effect=lambda *args,**kwargs:events.append('record')
    executor=module.SupabaseLiveExecutor(reader=SimpleNamespace(read_candles=lambda *args,**kwargs:candles),
        supabase=cloud,bybit=bybit,stake_amount=Decimal(6),shadow_observer=Broken())
    monkeypatch.setattr(module,'entry_signal',lambda *args,**kwargs:(True,[]))
    monkeypatch.setattr(executor,'_ml_entry_allows',lambda *args:(True,[]))
    result=executor.run_once('HYPE/USDT',live=True,now=candles[-1].open_time+timedelta(minutes=1))
    assert result.decision=='approve_entry' and events==['before','buy','after','record']
    assert any('cash_shadow_recording_error' in reason for reason in result.reasons)


def test_protocol_cannot_switch_between_two_pre_registered_candidates(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);manifest,_=candidate()
    manifest.update(artifact_sha256='a'*64,protocol_sha256='b'*64)
    selected=time(manifest['selected_at']);ledger.clock=lambda:selected;raw=json.dumps(manifest,sort_keys=True).encode()
    ledger.freeze_candidate(raw,registered_at=selected)
    other={**manifest,'artifact_sha256':'c'*64,'selected_at':(selected+timedelta(seconds=1)).isoformat()}
    with pytest.raises(sqlite3.IntegrityError):
        ledger.freeze_candidate(json.dumps(other).encode(),registered_at=selected+timedelta(seconds=1))
    assert ledger.frozen_manifest('b'*64)==raw


def test_broker_order_link_proves_request_order_even_when_server_clock_is_behind(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START);record(ledger)
    ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START+timedelta(seconds=1),order_link_id='o1')
    rows=outcomes();rows[0]['entry_at']=(TEST_START-timedelta(seconds=2)).isoformat()
    report=compare_factual_cohort(ledger.rows(),rows,PROTOCOL,candidate_sha='a'*64,split='sealed_test',as_of=TEST_END)
    assert report['matched_factual_buys']==1
    with pytest.raises(ValueError,match='broker order link'):
        ledger.bind_order('a'*64,'o1','buy1',bound_at=TEST_START+timedelta(seconds=2),order_link_id='wrong')


def test_old_prediction_and_selection_dates_cannot_be_backfilled(tmp_path):
    ledger=ShadowLedger(tmp_path/'ledger.sqlite',clock=lambda:TEST_START+timedelta(days=1))
    with pytest.raises(ValueError,match='retrospectively'):record(ledger)
    manifest,_=candidate();manifest.update(artifact_sha256='a'*64,protocol_sha256='b'*64)
    with pytest.raises(ValueError,match='retrospectively'):
        ledger.freeze_candidate(json.dumps(manifest).encode(),registered_at=time(manifest['selected_at']))


@pytest.mark.parametrize('field,value,reason',[
    ('feature_names',['rsi_14']*7,'feature ordering'),
    ('threshold',.75,'threshold differs'),
    ('live_eligible',True,'must not be live eligible')])
def test_candidate_schema_cannot_silently_reorder_features_or_change_threshold(field,value,reason):
    manifest,artifact=candidate();artifact[field]=value
    with pytest.raises(ValueError,match=reason):validate_candidate(manifest,artifact,PROTOCOL,now=TEST_START)


def test_candidate_training_time_cannot_precede_known_labels():
    manifest,artifact=candidate()
    artifact['trained_at']=(time(artifact['config']['fit_information_end'])-timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='before its information'):validate_candidate(manifest,artifact,PROTOCOL,now=TEST_START)
