from copy import deepcopy
import pytest
from cryptoforge.fifo_conservation_audit import audit_conservation
from cryptoforge.live_trade_journal import reconstruct_trades
from test_live_trade_journal import fill


def fixture():
    fills=[fill('b1','Buy','2','10'),fill('b2','Buy','3','20',time=1100),
           fill('s','Sell','3','30',fee='.1',time=2000)]
    rows,_=reconstruct_trades(fills)
    return fills,rows


def test_complete_fifo_conserves_remaining_inventory_and_basis():
    fills,rows=fixture();result=audit_conservation(fills,rows)
    assert result['closed_allocations_checked']==2
    assert result['remaining_records_checked']==2
    assert result['open_basis']=='40'
    assert result['open_lots']==1


def test_valid_per_segment_math_cannot_hide_wrong_fifo_order():
    fills,rows=fixture()
    rows=deepcopy(rows)
    # A later lot cannot cover more than the one unit left after the first lot.
    row=next(row for row in rows if row['external_trade_id']=='bybit:spot:fifo:b2:s')
    row['amount']='2'
    with pytest.raises(ValueError,match='conservation'):
        audit_conservation(fills,rows)


def test_missing_open_inventory_record_is_not_a_complete_replay():
    fills,rows=fixture();rows=[row for row in rows if row['status']!='open']
    with pytest.raises(ValueError,match='remaining acquisition record'):
        audit_conservation(fills,rows)


def test_extra_segment_cannot_duplicate_closed_profit():
    fills,rows=fixture();extra=deepcopy(rows[0]);extra['external_trade_id']='extra';rows.append(extra)
    with pytest.raises(ValueError,match='unmatched extra'):
        audit_conservation(fills,rows)
