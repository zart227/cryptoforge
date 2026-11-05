from copy import deepcopy
import pytest
from cryptoforge.execution_loss_review import review_losses
from cryptoforge.live_trade_journal import reconstruct_trades
from test_live_trade_journal import fill


def test_fee_erased_case_preserves_original_segment_and_no_strategy_claim():
    rows,_=reconstruct_trades([fill('b','Buy','1','100',fee='1'),
                              fill('s','Sell','1','100',fee='1',time=2000)])
    result=review_losses(rows)
    assert result['loss_at_least_one_percent_segments']==1
    assert result['fee_equivalent_erased_nonnegative_segments']==1
    case=result['recent_cases'][0]
    assert case['source_segment']['realized_pnl']=='-2'
    assert not case['strategy_attribution_known']
    assert not case['counterfactual_no_fee_profit_certified']


def test_unknown_fees_remain_unknown_and_are_not_zero_loss():
    rows,_=reconstruct_trades([fill('b','Buy','1','100',fee='1',currency='BNB'),
                              fill('s','Sell','1','90',time=2000)])
    result=review_losses(rows)
    assert result['unknown_fee_or_pnl_segments']==1
    assert result['known_closed_segments']==0 and not result['recent_cases']


def test_duplicate_fifo_case_cannot_double_loss_counts():
    rows,_=reconstruct_trades([fill('b','Buy','1','100'),fill('s','Sell','1','90',time=2000)])
    closed=next(row for row in rows if row['status']=='closed')
    with pytest.raises(ValueError,match='unique FIFO'):
        review_losses([closed,deepcopy(closed)])
