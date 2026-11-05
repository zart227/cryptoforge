"""Original UTC day anchors and overnight fees survive independent replay."""
from datetime import timedelta
from decimal import Decimal as D
from fractions import Fraction

from test_paper_worker_replay_v2 import setup,audit
from test_paper_worker_capture_v2 import tick,prediction
from test_paper_valuation_capture import raw_market
from test_paper_wallet import START


def test_original_day_anchor_carry_and_exact_pnl_across_utc_midnight(tmp_path):
    start=START.replace(hour=23,minute=59,second=50);end=start+timedelta(seconds=30)
    worker,clock,registered=setup(tmp_path,start=start,end=end)
    clock.now=start;tick(worker,clock,[prediction(clock)])
    clock.advance(5);tick(worker,clock)
    worker._market=lambda pair:raw_market(clock,pair,price='95')
    for _ in range(4):clock.advance(5);tick(worker,clock)
    clock.now=end;q,r=raw_market(clock,price='95')
    worker.mark_endpoint({q['pair']:q},{r['pair']:r});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_fifo_replay_pass'] and result['full_worker_decision_replay_pass']
    assert result['coverage_evidence_pass'] and result['fills_checked']==2
    anchors=list(worker._source.iter_rows('wallet.day_anchors'))
    assert len(anchors)==2 and anchors[0][0]!=anchors[1][0]
    assert D(anchors[1][1])>D(result['final_equity'])
    basis=sum((Fraction(D(r[4])) for r in worker._source.iter_rows('wallet.lots')),Fraction(0))
    assert Fraction(D(result['final_cash']))+basis==100+Fraction(D(result['allocated_realized_pnl']))
