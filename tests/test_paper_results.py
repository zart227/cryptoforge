from datetime import UTC,datetime,timedelta
from decimal import Decimal
import pytest
from cryptoforge.paper_results import export_results
from test_paper_worker import setup,prediction,tick
from test_paper_wallet import market


def test_export_is_simulated_and_never_becomes_real_training_labels(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    clock.advance(3601);tick(worker,rows);clock.advance();tick(worker,rows)
    result=export_results(wallet.path,worker.path,as_of=clock.now)
    assert len(result['campaigns'])==1 and result['simulated'] is True
    row=result['campaigns'][0]
    assert row['source_prediction']['opportunity']=='op1'
    assert Decimal(row['cash_recovery_net_dust_zero'])==Decimal(row['closed_net_pnl'])-Decimal(row['remaining_basis'])
    assert not result['real_training_examples_allowed'] and not result['live_promotion_allowed']


def test_current_inventory_cannot_backfill_an_old_balance(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    with pytest.raises(ValueError,match='earlier paper'):
        export_results(wallet.path,worker.path,as_of=clock.now-timedelta(seconds=1))


def test_export_does_not_initialize_missing_wallet(tmp_path):
    result=export_results(tmp_path/'missing.sqlite',tmp_path/'worker.sqlite',as_of=datetime.now(UTC))
    assert result['status']=='paper_not_started' and not (tmp_path/'missing.sqlite').exists()


def test_corrupt_cost_basis_fails_reconciliation(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    db=wallet._db();db.execute("UPDATE lots SET cost='1000'");db.commit();db.close()
    with pytest.raises(ValueError,match='basis is not conserved'):
        export_results(wallet.path,worker.path,as_of=clock.now)


def test_minute_compression_retains_hidden_drawdown_and_missing_mark(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance();tick(worker,rows)
    quote,filters=market(clock,price='50')
    wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters});wallet.mark({})
    quote,filters=market(clock,price='110')
    wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    result=export_results(wallet.path,worker.path,as_of=clock.now)
    assert len(result['equity_marks'])==1
    assert result['mark_quality']['all_marks_known'] is False
    assert Decimal(result['mark_quality']['max_drawdown'])>Decimal('.05')


def test_expired_queued_buy_remains_visible_in_export(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);clock.advance(31);tick(worker,rows)
    report=export_results(wallet.path,worker.path,as_of=clock.now)
    assert report['execution_counts']['Buy:rejected']==1
    assert report['rejection_reasons']['Buy:source_prediction_expired']==1
    assert not report['campaigns'] and not report['fills']


def test_future_rejection_without_fill_cannot_backfill_old_paper_state(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path);rows=[prediction(clock)]
    tick(worker,rows);before=clock.now
    clock.advance(31);wallet.cancel_pending(wallet.pending_intents()[0]['id'],'expired_source')
    with pytest.raises(ValueError,match='earlier paper decision'):
        export_results(wallet.path,worker.path,as_of=before)
    result=export_results(wallet.path,worker.path,as_of=clock.now)
    assert result['execution_counts']['Buy:rejected']==1 and not result['fills']


def test_future_worker_event_without_quality_error_is_still_unavailable(tmp_path):
    clock,wallet,worker,calls=setup(tmp_path)
    before=clock.now;clock.advance();worker._event({'status':'later_diagnostic'})
    with pytest.raises(ValueError,match='earlier paper worker'):
        export_results(wallet.path,worker.path,as_of=before)
