from copy import deepcopy
from datetime import datetime, UTC
import pytest
from cryptoforge.live_feedback import analyze_feedback
from test_live_feedback import row


def context():
    return {'pair':'ETH/USDT','decided_at':'2026-10-07T05:00:00+00:00',
            'decision':'approve_entry','features':{'order':{'result':{'orderId':'buy1'}}},
            'reasons':['bounce=True']}


@pytest.mark.parametrize('reverse',[False,True])
def test_conflicting_context_does_not_choose_last_logged_strategy(reverse):
    first=context();second=deepcopy(first);second['reasons']=['breakout=True']
    decisions=[first,second,deepcopy(first)]
    if reverse:decisions.reverse()
    report=analyze_feedback([row()],decisions,as_of=datetime(2026,10,7,6,tzinfo=UTC))
    assert report['conflicting_order_contexts']==1
    assert not report['entry_cohorts']
    assert report['exact_entry_cost_coverage_fraction']=='0'
    assert report['outcomes'][0]['entries'][0]['context_match']=='missing'
    assert report['summary']['closed_exit_orders']==1


def test_identical_duplicates_preserve_single_attribution():
    first=context()
    report=analyze_feedback([row()],[first,deepcopy(first)],as_of=datetime(2026,10,7,6,tzinfo=UTC))
    assert report['conflicting_order_contexts']==0
    assert report['entry_cohorts'][0]['entry_flags']=='bounce|spot_order'
    assert report['exact_entry_cost_coverage_fraction']=='1'
