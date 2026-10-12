from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json

from cryptoforge.paper_worker import PaperWorker
from cryptoforge.paper_wallet import PaperWallet
from test_paper_wallet import Clock,START,config,market


def setup(tmp_path,*,indicator=None):
    clock=Clock();wallet=PaperWallet(tmp_path/'wallet.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    policy=json.loads(Path('config/paper-execution-policy-v1.json').read_bytes())
    policy.update(enabled=True,status='frozen')
    calls=[]
    def quotes(pair):calls.append(pair);return market(clock,pair)
    worker=PaperWorker(wallet,tmp_path/'worker.sqlite',policy=policy,market=quotes,exit_indicator=indicator,clock=clock)
    return clock,wallet,worker,calls


def prediction(clock,op='op1',accept=True):
    return {'candidate_sha256':'a'*64,'opportunity':op,'pair':'AAA/USDT','predicted_at':clock.now.isoformat(),
            'observed_at':clock.now.isoformat(),'would_enter':accept}


def tick(worker,rows):return worker.tick(rows,window_start=START,window_end=START+timedelta(days=2))


def test_forward_ticks_enqueue_then_use_a_later_quote(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);assert not wallet.snapshot()['fills'] and len(wallet.pending_intents())==1
    clock.advance();tick(worker,rows)
    assert len(wallet.snapshot()['fills'])==1 and wallet.snapshot()['fills'][0]['mode']=='paper'
    tick(worker,rows);assert len(wallet.snapshot()['fills'])==1


def test_rejected_prediction_and_disabled_policy_cannot_spend_cash(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path)
    tick(worker,[prediction(clock,accept=False)])
    assert not wallet.pending_intents() and not calls
    worker.policy['enabled']=False
    assert tick(worker,[prediction(clock,'op2')])['status']=='paper_policy_disabled'
    assert not calls and not wallet.snapshot()['fills']


def test_original_prediction_expiry_does_not_reset_on_enqueue(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    clock.advance(29);tick(worker,rows);assert wallet.pending_intents()
    clock.advance(2);tick(worker,rows)
    assert not wallet.pending_intents() and not wallet.snapshot()['fills']


def test_hold_timeout_enqueues_sell_before_later_execution(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    clock.advance(3601);tick(worker,rows)
    assert any(row['side']=='Sell' for row in wallet.pending_intents())
    clock.advance();tick(worker,rows)
    assert len(wallet.snapshot()['closed_segments'])==1


def test_unknown_market_does_not_create_simulated_fills(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    worker.market=lambda pair:(_ for _ in ()).throw(TimeoutError())
    report=tick(worker,rows)
    assert report['errors']['AAA/USDT']=='TimeoutError' and not wallet.snapshot()['fills']


def test_shared_exit_signal_is_used_and_state_survives_restart(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path,indicator=lambda pair:(True,['rsi_exit']))
    rows=[prediction(clock)];tick(worker,rows);clock.advance();tick(worker,rows)
    assert any(row['side']=='Sell' for row in wallet.pending_intents())
    restored=PaperWorker(wallet,tmp_path/'worker.sqlite',policy=worker.policy,market=worker.market,
                         exit_indicator=lambda pair:(True,[]),clock=clock)
    clock.advance();tick(restored,rows)
    assert len(wallet.snapshot()['fills'])==2


def test_last_day_closes_positions_and_never_opens_new_entries(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    cutoff=clock.now;rows.append(prediction(clock,'op2'))
    report=worker.tick(rows,window_start=START,window_end=START+timedelta(days=2),entry_cutoff=cutoff)
    assert report['new_intents']==0 and any(r['side']=='Sell' for r in wallet.pending_intents())


def test_hard_stop_does_not_depend_on_optional_exit_indicator(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path,indicator=lambda pair:(False,[]))
    rows=[prediction(clock)];tick(worker,rows);clock.advance();tick(worker,rows)
    clock.advance();worker.market=lambda pair:market(clock,pair,price='95')
    tick(worker,rows)
    assert any(r['side']=='Sell' for r in wallet.pending_intents())


def test_live_runtime_policy_mutation_is_not_an_implicit_new_strategy(tmp_path):
    import pytest
    clock,wallet,worker,calls=setup(tmp_path)
    worker.policy['exits']['stop_fraction']='.10'
    with pytest.raises(ValueError,match='cannot change in place'):tick(worker,[prediction(clock)])
    assert not calls


def test_prior_test_forecasts_do_not_pollute_paper_source_accounting(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path)
    old=prediction(clock,'old-test');old['predicted_at']=(START-timedelta(days=2)).isoformat()
    future_window=prediction(clock,'after-window');future_window['predicted_at']=(START+timedelta(days=3)).isoformat()
    current=prediction(clock,'current');tick(worker,[old,future_window,current])
    db=worker._db()
    try:seen=list(db.execute('SELECT status FROM seen_predictions'))
    finally:db.close()
    assert seen==[('queued',)] and len(wallet.pending_intents())==1


def test_future_forecast_inside_paper_interval_remains_a_quality_failure(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path)
    future=prediction(clock);future['predicted_at']=(clock.now+timedelta(hours=1)).isoformat()
    tick(worker,[future])
    db=worker._db()
    try:assert list(db.execute('SELECT status FROM seen_predictions'))==[('outside_window_or_future',)]
    finally:db.close()
    assert not wallet.pending_intents()


def test_exit_skipped_by_wall_budget_is_a_recorded_quality_error(tmp_path,monkeypatch):
    import cryptoforge.paper_worker as module
    clock,wallet,worker,calls=setup(tmp_path,indicator=lambda pair:(False,[]))
    rows=[prediction(clock)];tick(worker,rows);clock.advance();tick(worker,rows);clock.advance()
    times=iter([0,0,21])
    monkeypatch.setattr(module.monotonic_time,'monotonic',lambda:next(times))
    report=tick(worker,rows)
    assert report['errors']['exit:AAA/USDT']=='paper_exit_wall_budget_exhausted'
