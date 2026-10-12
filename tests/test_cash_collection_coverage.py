from datetime import UTC,datetime,timedelta
from cryptoforge.cash_collection_coverage import collection_coverage

NOW=datetime(2026,10,9,tzinfo=UTC)


def trade(order,status='closed',origin='cryptoforge',suffix='exit'):
    return {'pair':'AAA/USDT','mode':'live','status':status,'opened_at':(NOW-timedelta(days=1)).isoformat(),
            'entry_reason':f'FIFO execution=buy order={order} origin={origin}',
            'idempotency_key':f'bybit:spot:fifo:{order}:{suffix}'}


def test_multiple_closing_segments_and_remaining_rows_are_one_buy():
    rows=[trade('1'),trade('1',suffix='exit2'),trade('1','open',suffix='remaining'),trade('2','open'),trade('3')]
    result={'examples':[{'pair':'AAA/USDT','entry_order':'1'}],
            'excluded':[{'pair':'AAA/USDT','entry_order':'3','reason':'missing_original_features'}]}
    report=collection_coverage(rows,{('AAA/USDT','1'),('AAA/USDT','3')},result,source_as_of=NOW)
    assert report['distinct_bot_buy_orders']==3 and report['additional_training_examples']==0
    assert report['status_counts']=={'eligible_current_snapshot':1,'awaiting_first_closed_exit':1,'excluded:missing_original_features':1}


def test_uncovered_and_unexplained_buys_are_distinguished_without_inventing_labels():
    report=collection_coverage([trade('1'),trade('2'),trade('3',origin='external'),trade('4','cancelled')],
        {('AAA/USDT','2')},{'examples':[],'excluded':[]},source_as_of=NOW)
    assert report['distinct_bot_buy_orders']==2
    assert report['unexplained_omissions']==1
    assert report['status_counts']['outside_current_verified_audit_coverage']==1


def test_future_acquisitions_do_not_enter_current_coverage():
    future=trade('future');future['opened_at']=(NOW+timedelta(seconds=1)).isoformat()
    report=collection_coverage([future],set(),{'examples':[],'excluded':[]},source_as_of=NOW)
    assert report['distinct_bot_buy_orders']==0
