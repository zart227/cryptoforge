"""Equal-clock, reverse-ID FIFO checked against distinct native row deltas.

This fixture seeds two original buys to isolate wallet accounting. It is not a
whole-controller trace and grants no trading or strategy qualification.
"""
from datetime import timedelta
from decimal import Decimal as D
from fractions import Fraction
import json

import pytest

from cryptoforge.paper_capture_state_v2 import _active,_logical,_delta
from cryptoforge.paper_replay_math_v2 import arithmetic
from cryptoforge.paper_wallet_replay_v2 import _Replay,_Scratch
from test_paper_worker_capture_v2 import setup as capture_setup
from test_paper_worker_replay_v2 import policy
from test_paper_valuation_capture import raw_market
from test_paper_wallet import START,config


def seeded_wallet(tmp_path):
    worker,clock=capture_setup(tmp_path,config=config(slippage=D(0),entry_fee=D(0),exit_fee=D(0)))
    source=worker._source
    version=worker.protocol['kernel_contract']['producer_version']
    with source.wallet._db() as db:
        for seq,identity,qty,cost in [(1,'z-original','1','6'),(2,'a-later','2','12')]:
            db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,NULL)',(identity,'AAA/USDT','Buy',START.isoformat(),START.isoformat(),'filled'))
            db.execute('INSERT INTO lots VALUES (?,?,?,?,?,?)',(identity,'AAA/USDT',START.isoformat(),qty,cost,'0'))
            fill=dict(producer_version=version,fill_sequence=seq,intent_id=identity,pair='AAA/USDT',side='Buy',mode='paper',
                candidate_sha256=worker.protocol['candidate_sha256'],filled_at=START.isoformat(),price='6',quantity=qty,cost=cost)
            db.execute('INSERT INTO fills VALUES (?,?)',(identity,json.dumps(fill,sort_keys=True)))
            db.execute('INSERT INTO fill_order(sequence,intent_id) VALUES (?,?)',(seq,identity))
        db.execute("UPDATE state SET value='82' WHERE key='cash'")
    clock.now=START+timedelta(seconds=1)
    source.wallet.enqueue('sell','AAA/USDT','Sell',created_at=clock.now)
    scratch=_Scratch(tmp_path/'independent.sqlite',policy())
    replay=_Replay(worker.protocol,source.manifest_sha256,scratch,policy(),worker.lifecycle)
    active=_active(source)
    for name in active:
        for row in active[name].values():
            if name=='wallet.state' and row[0]!='cash' or name=='worker.state':continue
            replay._put(name,row)
    replay.cash='82';replay.fills=2
    # Deliberately use lexical insertion order to prove the explicit causal index.
    replay.lots={r[0]:r for r in active['wallet.lots'].values()}
    replay.lot_order={'z-original':1,'a-later':2}
    assert list(replay.lots)==['a-later','z-original']
    replay.changes={};scratch.db.commit()
    return worker,clock,replay,scratch


@pytest.mark.parametrize('step',['.5','.7','1e-28'])
def test_causal_index_controls_fifo_with_exact_partial_allocations(tmp_path,step):
    worker,clock,replay,scratch=seeded_wallet(tmp_path)
    source=worker._source;clock.now=START+timedelta(seconds=6)
    quote,rule=raw_market(clock,price='10',step=step)
    before=_active(source);cache={};point=_logical(source,before,cache)
    observations=[]
    def observed():observations.append(clock.now.isoformat());return clock.now
    source.wallet.clock=observed
    try:
        with arithmetic():
            result=source.wallet.execute('sell',quote,rule,entry_cutoff=START+timedelta(seconds=15))
            after=_active(source)
            complete=dict(at=clock.now.isoformat(),native_clocks=observations,result=result,
                changes=_delta(source,before,after),after=_logical(source,after,cache))
            prepared=dict(at=clock.now.isoformat(),operation='execute',before=point,
                inputs=dict(intent_id='sell',quote=quote,filters=rule,entry_cutoff=(START+timedelta(seconds=15)).isoformat()))
            replay.operation(prepared,complete)
        assert replay.segments==2 and list(source.iter_rows('wallet.fill_order'))[-1]==(3,'sell')
        segments=[json.loads(row[1]) for row in source.iter_rows('wallet.closed_segments')]
        assert [r['entry_intent'] for r in segments]==['z-original','a-later']
        assert segments[0]['cost']=='6'
        assert Fraction(D(replay.cash))+sum((Fraction(D(r[4])) for r in replay.lots.values()),Fraction(0))==100+Fraction(replay.realized)
        assert replay.summary==complete['after']['sources']
    finally:scratch.db.close()
