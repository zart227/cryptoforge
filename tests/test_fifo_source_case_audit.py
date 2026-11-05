from copy import deepcopy
import pytest
from cryptoforge.fifo_case_audit import audit_segment
from cryptoforge.live_trade_journal import reconstruct_trades
from test_live_trade_journal import fill


def fixture():
    fills=[fill('b','Buy','10','2',fee='.1',currency='ETH'),
           fill('s','Sell','4','3',fee='.2',time=2000)]
    rows,_=reconstruct_trades(fills)
    return next(row for row in rows if row['status']=='closed'),fills


def test_partial_base_fee_acquisition_quote_fee_sale_replays_original_economics():
    segment,fills=fixture();result=audit_segment(segment,fills)
    assert result['arithmetic_passed'] and result['partial_acquisition_allocation']
    assert result['source_received_quantity']=='9.9'
    assert result['buy_fee_currency']=='ETH' and result['sell_fee_currency']=='USDT'
    assert not result['full_fifo_order_certified']


@pytest.mark.parametrize('field',['stake_amount','fee_amount','realized_pnl'])
def test_tampered_allocated_economics_rejected(field):
    segment,fills=fixture();segment[field]='0'
    with pytest.raises(ValueError,match='source allocation differs'):
        audit_segment(segment,fills)


def test_third_token_fee_is_unknown_without_original_conversion_source():
    segment,fills=fixture();fills[0]['feeCurrency']='BNB'
    with pytest.raises(ValueError,match='known base or quote fee'):
        audit_segment(segment,fills)


def test_duplicate_execution_inputs_cannot_change_allocation():
    segment,fills=fixture();fills.append(deepcopy(fills[0]))
    with pytest.raises(ValueError,match='unique original'):
        audit_segment(segment,fills)
