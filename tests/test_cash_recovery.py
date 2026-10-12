from copy import deepcopy
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
from decimal import Decimal
import pytest

from cryptoforge.cash_recovery import build_cash_recovery,TARGET_VERSION
from cryptoforge.experience_memory import remember_experiences,available_experiences
from test_live_experience import data

SEEN=datetime(2026,10,7,6,tzinfo=UTC)


def fixture():
    trades,contexts=data()
    trades[1].update(status='open',amount='.001',stake_amount='.005')
    observations={'ETH/USDT':{'category':'spot','observed_at':SEEN.isoformat(),
        'quote_observed_at':SEEN.isoformat(),'bid_price':'5',
        'instrument':{'symbol':'ETHUSDT','status':'Trading',
                      'lotSizeFilter':{'basePrecision':'.01','minOrderAmt':'5'}}}}
    return trades,contexts,observations


def build(args=None,**changes):
    kwargs=dict(observed_at=SEEN,source_as_of=SEEN,accounting_quality_verified=True)
    kwargs.update(changes)
    return build_cash_recovery(*(args or fixture()),**kwargs)


def test_cash_recovery_charges_unsold_basis_once_not_exit_fees_twice():
    result=build();row=result['examples'][0]
    assert row['target_version']==TARGET_VERSION and row['fully_closed'] is False
    assert Decimal(row['cash_recovery_net'])==Decimal('-.025')
    assert Decimal(row['cost'])==Decimal('5.005')
    assert row['example'].label==0 and row['actual_residual_inventory_preserved']
    assert result['automatic_training_allowed'] is False


def test_input_window_is_preserved_only_when_original_context_recorded_it():
    assert 'feature_input_contract' not in build()['examples'][0]
    args=fixture();features=args[1][0]['features']
    features.update(model_feature_calculation_contract='bounded-window-candle-v1',
        model_feature_lookback_candles=120,model_input_timeframe='5m',model_input_candle_state='closed_only')
    row=build(args)['examples'][0]
    assert row['feature_input_contract']['lookback_candles']==120
    features['model_feature_lookback_candles']=True
    result=build(args)
    assert not result['examples'] and result['excluded'][0]['reason']=='invalid_original_input_contract'


def test_input_contract_correction_gets_new_observation_version_not_backdated(tmp_path):
    args=fixture();first=build(args)
    def serial(report):return {**report,'examples':[{**r,'example':asdict(r['example'])} for r in report['examples']]}
    path=tmp_path/'memory.sqlite';remember_experiences(serial(first),path,observed_at=SEEN)
    args[1][0]['features'].update(model_feature_calculation_contract='bounded-window-candle-v1',
        model_feature_lookback_candles=120,model_input_timeframe='5m',model_input_candle_state='closed_only')
    later=SEEN+timedelta(minutes=1);remember_experiences(serial(build(args)),path,observed_at=later)
    old=available_experiences(path,target=TARGET_VERSION,as_of=SEEN)
    current=available_experiences(path,target=TARGET_VERSION,as_of=later)
    assert 'feature_input_contract' not in old[0]
    assert current[0]['feature_input_contract']['lookback_candles']==120


def test_conservative_cash_target_can_differ_from_positive_closed_portion():
    args=fixture();args[0][0]['realized_pnl']='.002'
    row=build(args)['examples'][0]
    assert Decimal(row['closed_net_pnl'])>0 and row['example'].label==0
    args[0][0]['realized_pnl']='.1'
    assert build(args)['examples'][0]['example'].label==1


def test_material_remaining_inventory_is_not_a_loss_label():
    args=fixture();args[0][1]['stake_amount']='.1'
    result=build(args)
    assert not result['examples'] and result['excluded'][0]['reason']=='material_residual_cost'


def test_observed_market_sellable_residual_is_not_dust():
    args=fixture();args[2]['ETH/USDT']['instrument']['lotSizeFilter']['basePrecision']='.00001'
    args[2]['ETH/USDT']['bid_price']='5000'
    result=build(args)
    assert not result['examples'] and result['excluded'][0]['reason']=='residual_market_sellable'


@pytest.mark.parametrize('change',['future','stale','missing','wrong_symbol'])
def test_unknown_or_future_instrument_observation_is_not_backfilled(change):
    args=fixture();obs=args[2]['ETH/USDT']
    if change=='future':obs['observed_at']=(SEEN+timedelta(seconds=1)).isoformat()
    elif change=='stale':obs['observed_at']=(SEEN-timedelta(minutes=6)).isoformat()
    elif change=='missing':args[2].clear()
    else:obs['instrument']['symbol']='BTCUSDT'
    assert not build(args)['examples']


def test_partial_fills_are_one_buy_example_and_future_closes_are_excluded():
    args=fixture();second=deepcopy(args[0][0]);second['idempotency_key']='bybit:spot:fifo:exec2:sell2'
    args[0].append(second)
    row=build(args)['examples'][0]
    assert row['source_segments']==2 and row['cost']=='10.005'
    second['closed_at']=(SEEN+timedelta(seconds=1)).isoformat()
    assert not build(args)['examples']


def test_external_exits_missing_features_and_unverified_accounting_excluded():
    args=fixture();args[0][0]['exit_reason']='FIFO order=sell1 origin=external'
    assert not build(args)['examples']
    args=fixture();args[1][0]['features']['feature_capture_status']='failed'
    assert not build(args)['examples']
    assert not build(accounting_quality_verified=False)['examples']
    assert not build(truncated=True)['examples']


def report(pnl='-.02'):
    args=fixture();args[0][0]['realized_pnl']=pnl
    result=build(args)
    result['examples']=[{**row,'example':asdict(row['example'])} for row in result['examples']]
    return result


def test_memory_keeps_first_seen_and_does_not_duplicate_repeated_samples(tmp_path):
    path=tmp_path/'memory.sqlite';first=report()
    remember_experiences(first,path,observed_at=SEEN)
    result=remember_experiences(first,path,observed_at=SEEN+timedelta(hours=1))
    assert result['stored_versions']==1 and result['distinct_buy_orders']==1
    known=available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=2))
    assert known[0]['label_available_at']==SEEN.isoformat()
    assert available_experiences(path,target=TARGET_VERSION,as_of=SEEN-timedelta(seconds=1))==[]


def test_late_correction_and_reversion_have_real_observation_times(tmp_path):
    path=tmp_path/'memory.sqlite'
    remember_experiences(report(),path,observed_at=SEEN)
    remember_experiences(report('.1'),path,observed_at=SEEN+timedelta(hours=2))
    remember_experiences(report(),path,observed_at=SEEN+timedelta(hours=3))
    before=available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=1))
    after=available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=2))
    reverted=available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=3))
    assert before[0]['example']['label']==0 and after[0]['example']['label']==1
    assert reverted[0]['example']['label']==0 and reverted[0]['label_available_at']==(SEEN+timedelta(hours=3)).isoformat()
    with pytest.raises(ValueError,match='backdate'):
        remember_experiences(report('.1'),path,observed_at=SEEN)


def test_candle_input_state_is_preserved_for_separate_future_evaluation():
    args=fixture();args[1][0]['features']['model_input_candle_state']='legacy_asof_snapshot'
    result=build(args)
    assert result['examples'][0]['input_candle_state']=='legacy_asof_snapshot'
    args[1][0]['features'].pop('model_input_candle_state')
    assert build(args)['examples'][0]['input_candle_state']=='unknown'


def test_verified_withdrawal_preserves_old_asof_and_reinstatement_is_new_version(tmp_path):
    path=tmp_path/'memory.sqlite';first=report();buy=first['examples'][0]
    remember_experiences(first,path,observed_at=SEEN)
    withdrawn={**first,'examples':[],'source_binding_verified':True,
        'excluded':[{'pair':buy['pair'],'entry_order':buy['entry_order'],'reason':'external_exit'}]}
    result=remember_experiences(withdrawn,path,observed_at=SEEN+timedelta(hours=1))
    assert result['distinct_buy_orders']==0 and result['withdrawn_buy_orders']==1
    assert len(available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(minutes=30)))==1
    assert available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=1))==[]
    repeat=remember_experiences(withdrawn,path,observed_at=SEEN+timedelta(hours=2))
    assert repeat['stored_versions']==2
    restored=remember_experiences(first,path,observed_at=SEEN+timedelta(hours=3))
    assert restored['stored_versions']==3 and restored['distinct_buy_orders']==1
    assert available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=3))[0]['label_available_at']==(SEEN+timedelta(hours=3)).isoformat()


@pytest.mark.parametrize('reason,verified,truncated',[('instrument_observation_unavailable',True,False),('external_exit',False,False),('external_exit',True,True)])
def test_missing_or_unverified_observation_does_not_withdraw_history(tmp_path,reason,verified,truncated):
    path=tmp_path/'memory.sqlite';first=report();buy=first['examples'][0]
    remember_experiences(first,path,observed_at=SEEN)
    excluded={**first,'examples':[],'source_binding_verified':verified,'snapshot_truncated':truncated,
        'excluded':[{'pair':buy['pair'],'entry_order':buy['entry_order'],'reason':reason}]}
    remember_experiences(excluded,path,observed_at=SEEN+timedelta(hours=1))
    assert len(available_experiences(path,target=TARGET_VERSION,as_of=SEEN+timedelta(hours=1)))==1
