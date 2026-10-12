from datetime import datetime,UTC
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from cryptoforge.live_feedback import analyze_feedback,candidate_cost_floor
from cryptoforge.supabase_executor import SupabaseLiveExecutor
from test_supabase_executor import support_bounce_candles


def row(identity='a',cost='5',pnl='-0.018',fee='0.018'):
    return {'idempotency_key':'bybit:spot:fifo:'+identity,'status':'closed','mode':'live','pair':'ETH/USDT',
            'opened_at':'2026-10-07T05:00:00+00:00','closed_at':'2026-10-07T05:02:30+00:00',
            'stake_amount':cost,'realized_pnl':pnl,'fee_amount':fee,
            'entry_reason':'FIFO order=buy1 origin=cryptoforge','exit_reason':'FIFO order=sell1 origin=cryptoforge'}


def test_net_pnl_is_not_charged_fees_twice_and_fifo_segments_grouped():
    rows=[row(),row('b','1','0.002','0.0036')]
    report=analyze_feedback(rows,[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    assert report['today']['closed_exit_orders']==1
    assert report['today']['net_pnl_usdt']=='-0.016'
    outcome=report['outcomes'][0]
    assert outcome['segments']==2 and Decimal(outcome['net_return'])==Decimal('-0.016')/6
    assert report['fee_accounting']=='net_pnl_already_includes_fees_do_not_subtract_again'
    assert outcome['fee_erased_gross_gain']
    assert outcome['exit_context_match']=='missing'
    with pytest.raises(ValueError,match='duplicate'):analyze_feedback([rows[0],rows[0]],[])


def test_future_outcomes_cannot_influence_cost_calibration():
    cutoff=datetime(2026,10,7,5,1,tzinfo=UTC)
    report=analyze_feedback([row()],[],as_of=cutoff)
    assert not report['outcomes']
    assert candidate_cost_floor(report,minimum_orders=1) is None
    previous=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    previous['accounting_quality_verified']=True
    assert candidate_cost_floor(previous,minimum_orders=1)==Decimal('0.0046')
    previous['trades_truncated']=True
    assert candidate_cost_floor(previous,minimum_orders=1) is None


def test_exact_order_attribution_and_unknown_fees_excluded():
    context={'pair':'ETH/USDT','decided_at':'2026-10-07T05:00:00+00:00','decision':'approve_entry',
             'features':{'order':{'result':{'orderId':'buy1'}},'entry_exit_conflict':True},'reasons':['emerging_momentum=True']}
    result=analyze_feedback([row()],[context],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    assert result['outcomes'][0]['entries'][0]['context_match']=='exact_order'
    assert result['outcomes'][0]['reentry_exit_conflict_observed'] is True
    assert result['entry_conflict_outcomes']['closed_exit_orders']==1
    assert result['entry_conflict_outcomes']['net_pnl_usdt']=='-0.018'
    assert any(h['kind']=='simultaneous_entry_exit_signals' for h in result['hypotheses'])
    assert result['automatic_live_changes_allowed'] is False
    unknown=row();unknown['fee_amount']=None
    report=analyze_feedback([unknown],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    assert not report['outcomes'] and report['excluded'][0]['reason']=='missing_cost_pnl_or_fees'


def test_actual_order_context_not_overwritten_by_same_bar_evaluation():
    client=Mock()
    executor=SupabaseLiveExecutor(reader=SimpleNamespace(),supabase=client,bybit=SimpleNamespace())
    candles=support_bounce_candles()
    order={'result':{'orderId':'buy123'}}
    executor._record('ETH/USDT','approve_entry',[],candles,live=True,order=order)
    actual=client.upsert.call_args.args[1][0]
    executor._record('ETH/USDT','hold',[],candles,live=True)
    evaluation=client.upsert.call_args.args[1][0]
    assert actual['idempotency_key']!=evaluation['idempotency_key']
    assert actual['features']['feature_version']=='candle-v1'
    assert len(actual['features']['model_feature_values'])==7
    executor._record('ETH/USDT','approve_entry',[],candles,live=True,order=order)
    assert client.upsert.call_args.args[1][0]['idempotency_key']==actual['idempotency_key']
    assert client.upsert.call_args.kwargs['resolution']=='ignore-duplicates'


def test_training_cost_calibration_is_cut_off_at_train_information_end(tmp_path):
    import json
    from cryptoforge.model_training import ModelTrainingRunner
    from test_model_training import FakeReader,FakeSupabase,make_training_candles
    feedback=Mock()
    feedback.read.return_value={'outcomes':[{'fee_drag_fraction':'0.0036','exit_controlled_by_bot':True,'exit_kind':'spot_order'} for _ in range(5)],
                                'accounting_quality_verified':True,'summary':{'closed_exit_orders':5}}
    runner=ModelTrainingRunner(reader=FakeReader(make_training_candles()),supabase=FakeSupabase(),
        artifact_dir=tmp_path,epochs=1,feedback_reader=feedback,
        registry=SimpleNamespace(latest=lambda **kwargs:None))
    runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    artifact=json.loads(next(tmp_path.glob('*.json')).read_text());config=artifact['config']
    assert config['round_trip_cost']==pytest.approx(.0046)
    assert config['min_label_return']>=config['round_trip_cost']
    cutoff=feedback.read.call_args.kwargs['as_of']
    assert cutoff.isoformat()==config['training_label_end']
    assert config['training_label_end']<config['fit_information_end']<config['evaluation_information_end']


def test_feedback_failure_preserves_active_model(tmp_path):
    import json
    from cryptoforge.model_training import ModelTrainingRunner
    from test_model_training import FakeReader,FakeSupabase,make_training_candles
    feedback=Mock();feedback.read.side_effect=RuntimeError('unavailable')
    client=FakeSupabase()
    runner=ModelTrainingRunner(reader=FakeReader(make_training_candles()),supabase=client,
        artifact_dir=tmp_path,epochs=1,feedback_reader=feedback,
        registry=SimpleNamespace(latest=lambda **kwargs:None))
    runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert runner.last_promotion['reason']=='live_feedback_unavailable'
    assert client.upserts[-1][1][0]['event_type']=='model.candidate'


def test_experience_memory_is_idempotent_and_has_future_cutoff(tmp_path):
    from cryptoforge.feedback_memory import remember_report,prior_outcomes
    report=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    report['accounting_quality_verified']=True
    path=tmp_path/'memory.sqlite'
    observed=datetime(2026,10,7,6,tzinfo=UTC)
    remember_report(report,path,observed_at=observed);stored=remember_report(report,path,observed_at=observed)
    assert stored['stored_exit_orders']==1
    assert prior_outcomes(path,datetime(2026,10,7,5,1,tzinfo=UTC))==[]
    assert len(prior_outcomes(path,datetime(2026,10,7,6,tzinfo=UTC)))==1


def test_late_execution_correction_is_not_visible_in_earlier_learning_window(tmp_path):
    from cryptoforge.feedback_memory import remember_report,prior_outcomes
    original=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    original['accounting_quality_verified']=True
    path=tmp_path/'memory.sqlite'
    remember_report(original,path,observed_at=datetime(2026,10,7,6,tzinfo=UTC))
    corrected=analyze_feedback([row(pnl='0.01')],[],as_of=datetime(2026,10,7,8,tzinfo=UTC))
    corrected['accounting_quality_verified']=True
    remember_report(corrected,path,observed_at=datetime(2026,10,7,8,tzinfo=UTC))
    earlier=prior_outcomes(path,datetime(2026,10,7,7,tzinfo=UTC))
    later=prior_outcomes(path,datetime(2026,10,7,9,tzinfo=UTC))
    assert earlier[0]['net_pnl']=='-0.018'
    assert later[0]['net_pnl']=='0.01'


def test_external_conversion_fees_do_not_calibrate_bot_fee_floor():
    normal=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    normal['accounting_quality_verified']=True
    conversion={**normal['outcomes'][0],'fee_drag_fraction':'.021','exit_controlled_by_bot':False,'exit_kind':'conversion'}
    normal['outcomes'].append(conversion)
    assert candidate_cost_floor(normal,minimum_orders=1)==Decimal('.0046')


def test_unverified_fifo_snapshots_are_never_learning_memory(tmp_path):
    from cryptoforge.feedback_memory import remember_report,prior_outcomes
    report=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    path=tmp_path/'memory.sqlite'
    remember_report(report,path,observed_at=datetime(2026,10,7,6,tzinfo=UTC))
    assert prior_outcomes(path,datetime(2026,10,7,7,tzinfo=UTC))==[]


def test_training_reader_uses_observed_fee_version_not_retrospective_source(tmp_path):
    from cryptoforge.feedback_memory import remember_report,ObservedFeedbackReader
    original=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    original['accounting_quality_verified']=True
    path=tmp_path/'memory.sqlite'
    remember_report(original,path,observed_at=datetime(2026,10,7,6,tzinfo=UTC))
    corrected=analyze_feedback([row(fee='.2')],[],as_of=datetime(2026,10,7,8,tzinfo=UTC))
    corrected['accounting_quality_verified']=True
    remember_report(corrected,path,observed_at=datetime(2026,10,7,8,tzinfo=UTC))
    source=Mock();source.read.return_value=corrected
    reader=ObservedFeedbackReader(source,path)
    before=reader.read(as_of=datetime(2026,10,7,7,tzinfo=UTC))
    after=reader.read(as_of=datetime(2026,10,7,9,tzinfo=UTC))
    assert candidate_cost_floor(before,minimum_orders=1)==Decimal('.0046')
    assert candidate_cost_floor(after,minimum_orders=1)==Decimal('.041')
    source.read.return_value={**corrected,'accounting_quality_verified':False}
    assert candidate_cost_floor(reader.read(as_of=datetime(2026,10,7,9,tzinfo=UTC)),minimum_orders=1) is None


def test_missing_observation_memory_never_backfills_retrospective_fees(tmp_path):
    from cryptoforge.feedback_memory import ObservedFeedbackReader
    source=Mock();report=analyze_feedback([row()],[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    report['accounting_quality_verified']=True;source.read.return_value=report
    result=ObservedFeedbackReader(source,tmp_path/'absent.sqlite').read(as_of=datetime(2026,10,7,7,tzinfo=UTC))
    assert not result['outcomes'] and result['memory_available'] is False
    assert candidate_cost_floor(result,minimum_orders=1) is None


def test_order_context_retains_dated_raw_instrument_filters_without_backdating():
    client=Mock()
    executor=SupabaseLiveExecutor(reader=SimpleNamespace(),supabase=client,bybit=SimpleNamespace())
    snapshot={"pair":"ETH/USDT","observed_at":"2026-10-07T05:00:00+00:00",
              "raw":{"symbol":"ETHUSDT","lotSizeFilter":{"basePrecision":".000001","maxMarketOrderQty":"6000"}}}
    executor._last_instrument_snapshot=snapshot
    executor._record('ETH/USDT','approve_entry',[],support_bounce_candles(),live=True,order={'result':{'orderId':'buy1'}})
    saved=client.upsert.call_args.args[1][0]['features']['instrument_snapshot']
    assert saved['observed_at']==snapshot['observed_at']
    assert saved['raw']['lotSizeFilter']['maxMarketOrderQty']=='6000'
    executor._record('HYPE/USDT','hold',[],support_bounce_candles(),live=True)
    assert 'instrument_snapshot' not in client.upsert.call_args.args[1][0]['features']


def test_one_percent_bot_loss_decomposition_does_not_charge_fees_twice():
    rows=[row(cost='5',pnl='-0.05',fee='0.02'),{**row('b',cost='5',pnl='-0.06',fee='0.07'),'exit_reason':'FIFO order=sell2 origin=cryptoforge'},
          {**row('c',cost='5',pnl='-1',fee='0.02'),'exit_reason':'FIFO order=sell3 origin=manual'}]
    report=analyze_feedback(rows,[],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    diagnostic=report['large_bot_losses']
    assert diagnostic['closed_bot_exit_orders']==2
    assert diagnostic['fee_erased_nonnegative_gross_orders']==1
    example=next(r for r in diagnostic['examples'] if r['exit_order']=='sell1')
    assert Decimal(example['net_return_pct'])==-1
    assert Decimal(example['reported_fee_drag_pct'])==Decimal('.4')
    assert Decimal(example['gross_before_reported_fees_estimate_pct'])==Decimal('-.6')
    assert not diagnostic['causal_failure_reason_established']
