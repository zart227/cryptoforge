from decimal import Decimal
import pytest
from cryptoforge.conversion_journal import conversion_fills
from cryptoforge.live_trade_journal import reconstruct_trades
from test_live_trade_journal import fill,closed


def source():
    record={'accountType':'eb_convert_uta','exchangeTxId':'quote1','createdAt':'1900','status':'success',
            'subRecords':[{'fromCoin':'ETH','fromAmount':'10','toCoin':'USDT','toAmount':'19.6',
                           'feeCoin':'USDT','feeAmount':'.4','status':'success'}]}
    transactions=[{'id':'quote1_ETH1','type':'CURRENCY_SELL','currency':'ETH','change':'-10','transactionTime':'2000'},
                  {'id':'quote1_ETH2','type':'CURRENCY_BUY','currency':'USDT','change':'19.6','transactionTime':'2000'}]
    return [record],transactions


def test_conversion_consumes_old_inventory_and_keeps_new_sale_cost_basis():
    synthetic=conversion_fills(*source())
    fills=[fill('old','Buy','10','2'),*synthetic,
           fill('new','Buy','10','3',time=3000),fill('sale','Sell','10','2.8',time=4000)]
    rows,result=reconstruct_trades(fills)
    trades=closed(rows)
    conversion=next(r for r in trades if 'conversion:' in r['exit_reason'])
    sale=next(r for r in trades if 'order-sale' in r['exit_reason'])
    assert Decimal(conversion['realized_pnl'])==Decimal('-.4')
    assert Decimal(conversion['fee_amount'])==Decimal('.4')
    assert Decimal(sale['realized_pnl'])==Decimal('-2')
    assert 'origin=external' in conversion['exit_reason']
    assert result.executions==3 and result.conversion_events==1


def test_unverified_proceeds_cannot_create_synthetic_accounting():
    records,transactions=source();transactions.pop()
    with pytest.raises(ValueError,match='proceeds'):conversion_fills(records,transactions)
    records,transactions=source();records[0]['subRecords'][0]['feeCoin']='OTHER'
    with pytest.raises(ValueError,match='fee currency'):conversion_fills(records,transactions)


def test_conversion_upgrade_supersedes_wrong_old_fifo_segment_atomically(tmp_path):
    from types import SimpleNamespace
    from datetime import datetime,UTC
    from test_live_trade_journal import Store
    from cryptoforge.live_trade_journal import sync_live_journal
    fills=[fill('old','Buy','10','2'),fill('new','Buy','10','3',time=3000),fill('sale','Sell','10','2.8',time=4000)]
    bybit=SimpleNamespace(get_spot_executions=lambda **kw:fills)
    store=Store();path=tmp_path/'journal.sqlite';now=datetime(1970,1,2,tzinfo=UTC)
    sync_live_journal(bybit=bybit,supabase=store,cache_path=path,now=now)
    old_key='bybit:spot:fifo:old:sale'
    assert store.rows[('trades',old_key)]['status']=='closed'
    records,transactions=source()
    bybit.get_small_conversion_history=lambda **kw:records
    bybit.get_unified_transactions=lambda **kw:transactions
    sync_live_journal(bybit=bybit,supabase=store,cache_path=path,now=now)
    assert store.rows[('trades',old_key)]['status']=='cancelled'
    assert store.rows[('trades',old_key)]['realized_pnl'] is None
    sale=store.rows[('trades','bybit:spot:fifo:new:sale')]
    assert Decimal(sale['realized_pnl'])==Decimal('-2')


def test_unmodeled_balance_change_blocks_misleading_publish(tmp_path):
    from types import SimpleNamespace
    from datetime import datetime,UTC
    from test_live_trade_journal import Store
    from cryptoforge.live_trade_journal import sync_live_journal
    bybit=SimpleNamespace(get_spot_executions=lambda **kw:[fill('buy','Buy','10','2')],
        get_small_conversion_history=lambda **kw:[],get_unified_transactions=lambda **kw:[
            {'id':'external','type':'TRANSFER_OUT','currency':'ETH','change':'-10','transactionTime':'2000'}])
    store=Store()
    with pytest.raises(ValueError,match='balance movements'):
        sync_live_journal(bybit=bybit,supabase=store,cache_path=tmp_path/'journal.sqlite',now=datetime(1970,1,2,tzinfo=UTC))
    assert not store.rows
