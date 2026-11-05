from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import json
import importlib.util
from pathlib import Path
import sqlite3
import random
import time
import tracemalloc

import pytest

import cryptoforge.paper_streaming_replay as streaming
from cryptoforge.paper_streaming_replay import ReplayPolicy, StreamingCoverage, audit_streaming_paper, register_replay
from cryptoforge.paper_lifecycle import CoverageTimeline
from test_paper_capture_v4 import setup as setup_capture, mark, fill, finish
from test_paper_capture_v4 import audit as audit_trace
from test_paper_capture_v3 import lifecycle
from test_paper_capture_v3 import storage as segment_policy
from test_native_paper_archive import policy as native_policy
from test_paper_wallet import START,config,market
from test_paper_valuation_capture import raw_market


def policy(**changes):
    return replace(ReplayPolicy(maximum_scratch_bytes=16*1024*1024,maximum_state_rows=20000,
        maximum_active_rows=128,maximum_active_bytes=1024*1024,maximum_wall_seconds=120,
        minimum_available_memory_bytes=1,minimum_free_disk_bytes=16*1024*1024),**changes)


def setup(tmp_path, replay_policy=None, **changes):
    wallet,clock = setup_capture(tmp_path,**changes)
    receipt = register_replay(tmp_path/'replay',capture_root=wallet.root,
        expected_registration_sha256=wallet.registration_sha256,policy=replay_policy or policy(),
        clock=lambda:START-timedelta(seconds=1))
    return wallet,clock,receipt


def audit(wallet,seal,replay,**changes):
    fields = dict(expected_registration_sha256=wallet.registration_sha256,
        expected_seal_sha256=seal['seal_sha256'],replay_root=replay['root'],
        expected_replay_registration_sha256=replay['replay_registration_sha256'],
        clock=lambda:START+timedelta(seconds=20))
    fields.update(changes)
    return audit_streaming_paper(wallet.root,**fields)


def test_streaming_cash_fees_fifo_negative_sale_archive_and_read_only(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock)
    assert fill(wallet,clock,'buy','Buy')['status'] == 'filled'
    wallet.compact();mark(wallet,clock)
    assert fill(wallet,clock,'sell','Sell',price='98')['status'] == 'filled'
    wallet.compact();clock.advance(2);mark(wallet,clock,price='98')
    seal = finish(wallet,clock)
    before = {str(p):p.read_bytes() for root in (wallet.root,Path(replay['root'])) for p in root.rglob('*') if p.is_file()}
    result = audit(wallet,seal,replay)
    assert result['full_fifo_replay_pass']
    assert result['fills_checked'] == 2 and result['segments_checked'] == 1
    assert result['raw_source_fills'] == 2 and result['raw_source_marks'] == 3
    assert D(result['final_cash']) < D(100)
    assert D(result['allocated_realized_pnl']) < 0 and D(result['fill_fee_quote_equivalent']) > 0
    assert not result['economic_profitability_established'] and not result['paper_evidence_pass']
    assert not result['live_admission_granted']
    assert before == {str(p):p.read_bytes() for root in (wallet.root,Path(replay['root'])) for p in root.rglob('*') if p.is_file()}


def test_fully_covered_cash_replay_does_not_establish_profitability(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    for second in (0,5,10,15,20):
        clock.now = START+timedelta(seconds=second);wallet.mark({},{})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['full_fifo_replay_pass'] and result['coverage_evidence_pass']
    assert result['coverage']['known_seconds'] == '20'
    assert result['final_equity'] == result['final_cash'] == '100'
    assert not result['paper_evidence_pass'] and not result['economic_profitability_established']


@pytest.mark.parametrize('marks', [[],[0],[0,0,0],[5,10,15],[0,5,10,15,20]])
def test_streaming_coverage_exactly_matches_existing_short_window_oracle(marks):
    limits = lifecycle();end = START+timedelta(seconds=20)
    old,new = CoverageTimeline(START,end,limits),StreamingCoverage(START,end,limits)
    for second in marks:
        at = START+timedelta(seconds=second)
        for timeline in (old,new):
            timeline.invalidate(at);timeline.mark(at,at+timedelta(seconds=6),sources_known=True)
    for timeline in (old,new):timeline.invalidate(end)
    assert old.finish() == new.finish()
    assert not hasattr(new,'intervals') and not hasattr(new,'mark_clocks')


def test_cancellation_pending_expiry_and_duplicate_terminal_replay(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    wallet.enqueue('cancel','AAA/USDT','Buy',created_at=clock.now)
    wallet.cancel_pending('cancel','operator_cancel')
    wallet.compact()
    assert wallet.execute('cancel',*raw_market(clock))['duplicate']
    assert not wallet.enqueue('cancel','AAA/USDT','Buy',created_at=clock.now)
    assert audit(wallet,finish(wallet,clock),replay)['fills_checked'] == 0


def test_pending_execution_waits_for_original_later_quote(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    wallet.enqueue('waiting','AAA/USDT','Buy',created_at=clock.now)
    assert wallet.execute('waiting',*raw_market(clock))['status'] == 'pending'
    clock.advance()
    assert wallet.execute('waiting',*raw_market(clock))['status'] == 'filled'
    assert audit(wallet,finish(wallet,clock),replay)['buys'] == 1


def test_multi_lot_fifo_includes_old_dust_basis_and_base_entry_fee(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock)
    fill(wallet,clock,'buy-one','Buy');fill(wallet,clock,'sell-one','Sell',price='98')
    mark(wallet,clock,price='98')
    fill(wallet,clock,'buy-two','Buy');mark(wallet,clock)
    fill(wallet,clock,'sell-two','Sell',price='98');mark(wallet,clock,price='98')
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['buys'] == result['sells'] == 2
    assert result['segments_checked'] == 3
    assert result['full_fifo_replay_pass']


@pytest.mark.parametrize('fault',['fee','cash','lot','segment'])
def test_self_consistent_source_capture_does_not_validate_wrong_native_accounting(tmp_path,monkeypatch,fault):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock)
    if fault == 'segment':fill(wallet,clock,'buy','Buy')
    original = wallet._source.wallet.execute
    def wrong(*args):
        result = original(*args)
        assert result['status'] == 'filled'
        with wallet._source.wallet._db() as db:
            if fault == 'fee':
                result['fill']['fee_amount'] = '0'
                db.execute('UPDATE fills SET payload=? WHERE intent_id=?',
                    (json.dumps(result['fill'],sort_keys=True),result['fill']['intent_id']))
            elif fault == 'cash':db.execute("UPDATE state SET value='95' WHERE key='cash'")
            elif fault == 'lot':db.execute("UPDATE lots SET qty='0.06'")
            else:
                identity,raw = db.execute('SELECT id,payload FROM closed_segments ORDER BY id LIMIT 1').fetchone()
                row = json.loads(raw);row['cost'] = '1'
                db.execute('UPDATE closed_segments SET payload=? WHERE id=?',(json.dumps(row,sort_keys=True),identity))
        return result
    monkeypatch.setattr(wallet._source.wallet,'execute',wrong)
    fill(wallet,clock,'sale' if fault == 'segment' else 'buy','Sell' if fault == 'segment' else 'Buy',price='98')
    seal = finish(wallet,clock)
    assert audit_trace(wallet,seal)['source_checkpoint_trace_pass']
    with pytest.raises(ValueError,match='independent'):audit(wallet,seal,replay)


def test_original_expired_intent_rejection_is_replayed(tmp_path):
    wallet,clock,replay = setup(tmp_path,config=config(signal_expiry_seconds=2))
    wallet.enqueue('expiry','AAA/USDT','Buy',created_at=clock.now);clock.advance(3)
    assert wallet.execute('expiry',*raw_market(clock))['reason'] == 'expired_signal'
    assert audit(wallet,finish(wallet,clock),replay)['fills_checked'] == 0


@pytest.mark.parametrize('kind',['inventory','cash','depth','daily'])
def test_original_native_rejection_decisions_are_independently_replayed(tmp_path,kind):
    changes = {'config':config(capital=D(6))} if kind == 'cash' else {}
    wallet,clock,replay = setup(tmp_path,**changes)
    if kind in {'inventory','cash','daily'}:
        fill(wallet,clock,'first','Buy')
        if kind == 'daily':mark(wallet,clock,price='50')
        else:mark(wallet,clock)
    if kind == 'inventory':result = fill(wallet,clock,'second','Buy')
    elif kind == 'cash':result = fill(wallet,clock,'second','Buy',pair='BBB/USDT')
    elif kind == 'depth':result = fill(wallet,clock,'second','Buy',depth='1')
    else:result = fill(wallet,clock,'second','Buy',pair='BBB/USDT')
    assert result['status'] == 'rejected'
    assert audit(wallet,finish(wallet,clock),replay)['full_fifo_replay_pass']


def test_raw_source_expiry_cannot_be_extended_by_repeating_old_book(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock);fill(wallet,clock,'buy','Buy')
    quote,rule = raw_market(clock)
    for second in (5,10,15,20):
        clock.now = START+timedelta(seconds=second)
        wallet.mark({'AAA/USDT':quote},{'AAA/USDT':rule})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['full_fifo_replay_pass']
    assert not result['coverage_evidence_pass']
    assert D(result['coverage']['known_seconds']) < 12


def test_material_inventory_marked_conditionally_at_zero_is_unknown_time(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    fill(wallet,clock,'buy','Buy')
    for second in (5,10,15,20):
        clock.now = START+timedelta(seconds=second);mark(wallet,clock,price='1')
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['full_fifo_replay_pass'] and result['material_zero_marks'] == 4
    assert result['coverage']['known_seconds'] == '0'
    assert not result['coverage_evidence_pass'] and result['material_inventory_pairs'] == ['AAA/USDT']


def test_normalized_only_fill_never_becomes_raw_source_evidence(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    wallet.execute('buy',*market(clock))
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['full_fifo_replay_pass'] and result['raw_source_fills'] == 0
    assert not result['lifecycle_checks']['raw_fill_sources'] and not result['coverage_evidence_pass']


def test_early_reader_opens_only_capture_registration_and_protocol(tmp_path,monkeypatch):
    wallet,clock,replay = setup(tmp_path)
    for name in ('storage','native','capture.lock'):(wallet.root/name).rename(wallet.root/(name+'.hidden'))
    Path(replay['root'],'registration.json').unlink()
    monkeypatch.setattr(streaming,'_registration',lambda *a,**k:pytest.fail('replay metadata read early'))
    result = audit_streaming_paper(wallet.root,expected_registration_sha256=wallet.registration_sha256,clock=clock)
    assert result['performance_hidden'] and not result['full_fifo_replay_pass']


def test_replay_cannot_be_registered_after_original_window_starts(tmp_path):
    wallet,clock = setup_capture(tmp_path)
    with pytest.raises(ValueError,match='preregistered'):
        register_replay(tmp_path/'late',capture_root=wallet.root,expected_registration_sha256=wallet.registration_sha256,
            policy=policy(),clock=clock)
    assert not (tmp_path/'late').exists()


@pytest.mark.parametrize('kind',['scratch_source','scratch_replay','policy_pin','capture_pin','replay_alias'])
def test_scratch_and_replay_identity_cannot_modify_or_adopt_sources(tmp_path,kind):
    wallet,clock,replay = setup(tmp_path);seal = finish(wallet,clock)
    changes = {}
    if kind == 'scratch_source':changes['scratch_parent'] = wallet.root
    elif kind == 'scratch_replay':changes['scratch_parent'] = Path(replay['root'])
    elif kind == 'policy_pin':changes['expected_replay_registration_sha256'] = 'f'*64
    elif kind == 'capture_pin':changes['expected_registration_sha256'] = 'f'*64
    else:
        alias = tmp_path/'replay-alias';alias.symlink_to(replay['root'],target_is_directory=True);changes['replay_root'] = alias
    with pytest.raises((ValueError,OSError)):audit(wallet,seal,replay,**changes)


def test_temporary_index_is_removed_on_success_and_failure(tmp_path,monkeypatch):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock)
    seal = finish(wallet,clock);parent = tmp_path/'scratch';parent.mkdir()
    audit(wallet,seal,replay,scratch_parent=parent)
    assert list(parent.iterdir()) == []
    def failed(*a,**k):raise ValueError('forced replay failure')
    monkeypatch.setattr(streaming._Replay,'_guard',failed)
    with pytest.raises(ValueError,match='forced replay failure'):
        audit(wallet,seal,replay,scratch_parent=parent)
    assert list(parent.iterdir()) == []


def test_replay_row_budget_stops_without_touching_sources(tmp_path):
    wallet,clock,replay = setup(tmp_path,replay_policy=policy(maximum_state_rows=4))
    mark(wallet,clock);seal = finish(wallet,clock)
    with pytest.raises(ValueError,match='scratch row budget'):audit(wallet,seal,replay)


def test_cli_real_clock_no_asof_and_new_output_outside_sources(tmp_path,capsys):
    spec = importlib.util.spec_from_file_location('stream_cli',Path(__file__).resolve().parents[1]/'scripts/audit_paper_streaming.py')
    cli = importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    wallet,clock,replay = setup(tmp_path)
    args = ['--root',str(wallet.root),'--expected-registration-sha256',wallet.registration_sha256]
    with pytest.raises(SystemExit):cli.main(args+['--as-of',START.isoformat()])
    assert cli.main(args+['--output',str(wallet.root/'invalid')]) == 1
    seal = finish(wallet,clock)
    args += ['--expected-seal-sha256',seal['seal_sha256'],'--replay-root',replay['root'],
        '--expected-replay-registration-sha256',replay['replay_registration_sha256']]
    output = tmp_path/'result.json'
    assert cli.main(args+['--output',str(output)]) == 0
    assert json.loads(output.read_bytes())['full_fifo_replay_pass']
    assert cli.main(args+['--output',str(output)]) == 1


@pytest.mark.parametrize('seed',[0,1,17,100])
def test_streaming_coverage_matches_random_causal_unknown_and_duplicate_events(seed):
    rng = random.Random(seed);limits = lifecycle();end = START+timedelta(seconds=200)
    old,new = CoverageTimeline(START,end,limits),StreamingCoverage(START,end,limits)
    second = 0
    while second < 200:
        second = min(200,second+rng.randrange(0,4))
        at = START+timedelta(seconds=second)
        valid = at+timedelta(seconds=rng.randrange(-2,15))
        known = bool(rng.randrange(2))
        for timeline in (old,new):
            timeline.invalidate(at)
            if second % 3:timeline.mark(at,valid,sources_known=known)
    assert old.finish() == new.finish()


@pytest.mark.parametrize('fees,price,step',[
    (('0','0','0'),'100','.0001'),
    (('.00075','.0011','.00001'),'99.999999','.00001'),
    (('.0018','.0018','.0005'),'100000','.00000001'),
])
def test_decimal_fee_precision_rounding_and_residuals(fees,price,step,tmp_path):
    wallet,clock,replay = setup(tmp_path,config=config(entry_fee=D(fees[0]),exit_fee=D(fees[1]),slippage=D(fees[2])))
    fill(wallet,clock,'buy','Buy',price=price,step=step)
    fill(wallet,clock,'sell','Sell',price=price,step=step)
    assert audit(wallet,finish(wallet,clock),replay)['full_fifo_replay_pass']


def test_scratch_physical_page_limit_stops_index_growth(tmp_path):
    p = policy(maximum_scratch_bytes=131072,minimum_free_disk_bytes=131072)
    index = streaming._Scratch(tmp_path/'bounded.sqlite',p)
    try:
        with pytest.raises(sqlite3.DatabaseError,match='full'):
            for n in range(1000):
                index.put('wallet.intents',[str(n),'AAA/USDT','Buy',START.isoformat(),START.isoformat(),'rejected','x'*1024])
                index.db.commit()
        assert index.path.stat().st_size <= p.maximum_scratch_bytes
    finally:index.db.close()


@pytest.mark.parametrize('resource',['memory','disk','wall'])
def test_audit_resource_limits_are_not_waived(tmp_path,monkeypatch,resource):
    wallet,clock,replay = setup(tmp_path,replay_policy=policy(maximum_wall_seconds=1))
    seal = finish(wallet,clock)
    if resource == 'wall':
        ticks = iter((0,2*10**9));monkeypatch.setattr(streaming,'monotonic_ns',lambda:next(ticks))
    else:
        original = streaming.measure_resources
        key = 'available_memory_bytes' if resource == 'memory' else 'free_disk_bytes'
        monkeypatch.setattr(streaming,'measure_resources',lambda path:{**original(path),key:0})
    with pytest.raises(ValueError,match='budget|resource floor'):audit(wallet,seal,replay)


def test_bounded_active_pair_count_blocks_larger_cache(tmp_path):
    wallet,clock,replay = setup(tmp_path,replay_policy=policy(maximum_active_rows=16))
    rules = {}
    for n in range(17):
        q,r = raw_market(clock,f'PAIR{n}/USDT');rules[r['pair']] = r
    wallet.mark({},rules)
    with pytest.raises(ValueError,match='active state budget'):audit(wallet,finish(wallet,clock),replay)


def test_bounded_serialized_active_bytes_are_enforced(tmp_path):
    wallet,clock,replay = setup(tmp_path,
        replay_policy=policy(maximum_active_rows=128,maximum_active_bytes=128*1024),
        storage_policy=segment_policy(maximum_record_bytes=32768),
        native_policy=native_policy(maximum_active_rows=64,maximum_batch_bytes=1024*1024))
    for n in range(17):
        rules = {}
        for k in range(2):
            pair = f'PAIR{n*2+k}/USDT'
            rules[pair] = dict(pair=pair,observed_at=clock.now.isoformat(),raw_response={'padding':'x'*6000})
        wallet.mark({},rules);clock.advance(1)
    with pytest.raises(ValueError,match='active state budget'):audit(wallet,finish(wallet,clock),replay)


def test_completion_time_does_not_backdate_known_coverage(tmp_path,monkeypatch):
    wallet,clock,replay = setup(tmp_path)
    original = wallet._source.wallet.mark
    def slow(*args):
        result = original(*args)
        if clock.now < START+timedelta(seconds=20):clock.advance(1)
        return result
    monkeypatch.setattr(wallet._source.wallet,'mark',slow)
    for second in (0,5,10,15,20):
        clock.now = START+timedelta(seconds=second);wallet.mark({},{})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['coverage']['known_seconds'] == '16'
    assert not result['coverage_evidence_pass']


def test_pending_intent_cannot_be_ignored_at_completed_closeout(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    for second in (0,5,10,15,20):
        clock.now = START+timedelta(seconds=second)
        if second == 0:wallet.enqueue('pending','AAA/USDT','Buy',created_at=clock.now)
        wallet.mark({},{})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['coverage']['coverage_pass'] and result['pending_intents'] == 1
    assert not result['lifecycle_checks']['no_pending_intents'] and not result['coverage_evidence_pass']


def test_unknown_book_for_owned_inventory_is_not_known_time(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    fill(wallet,clock,'buy','Buy')
    for second in (5,10,15,20):
        clock.now = START+timedelta(seconds=second);wallet.mark({},{})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['full_fifo_replay_pass'] and result['final_equity'] is None
    assert result['coverage']['known_seconds'] == '0' and not result['coverage_evidence_pass']


def test_overnight_anchor_carries_last_known_equity(tmp_path):
    start = START.replace(hour=23,minute=59,second=55)
    wallet,clock,replay = setup(tmp_path,start=start,end=start+timedelta(seconds=20))
    clock.now = start;mark(wallet,clock)
    fill(wallet,clock,'overnight','Buy')
    clock.now = start+timedelta(seconds=6);mark(wallet,clock,price='98')
    clock.now = start+timedelta(seconds=20);wallet.terminate('completed');seal = wallet.finalize()
    assert audit(wallet,seal,replay,clock=clock)['full_fifo_replay_pass']
    assert len(list(wallet._source.iter_rows('wallet.day_anchors'))) == 2


def test_early_abort_stays_hidden_and_never_qualifies_lifecycle(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    mark(wallet,clock);wallet.terminate('operator_abort')
    assert audit_streaming_paper(wallet.root,expected_registration_sha256=wallet.registration_sha256,clock=clock)['performance_hidden']
    clock.now = START+timedelta(seconds=20);seal = wallet.finalize()
    result = audit(wallet,seal,replay)
    assert result['full_fifo_replay_pass'] and not result['lifecycle_checks']['completed']
    assert not result['coverage_evidence_pass']


def test_last_normalized_only_dust_mark_does_not_borrow_previous_raw_source(tmp_path):
    wallet,clock,replay = setup(tmp_path)
    wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance(1)
    wallet.execute('buy',*raw_market(clock))
    wallet.enqueue('sell','AAA/USDT','Sell',created_at=clock.now);clock.advance(1)
    wallet.execute('sell',*raw_market(clock,price='98'));mark(wallet,clock,price='98')
    for second in (5,10,15):
        clock.now = START+timedelta(seconds=second);mark(wallet,clock,price='98')
    clock.now = START+timedelta(seconds=20)
    q,r = market(clock,price='98');wallet.mark({q['pair']:q},{r['pair']:r})
    result = audit(wallet,finish(wallet,clock),replay)
    assert result['coverage']['coverage_pass'] and result['coverage']['covers_end']
    assert not result['lifecycle_checks']['final_valuation_source_verified'] and not result['coverage_evidence_pass']


def test_omitted_losing_fill_does_not_disappear_from_admission(tmp_path,monkeypatch):
    wallet,clock,replay = setup(tmp_path)
    fill(wallet,clock,'buy','Buy')
    original = wallet._source.wallet.execute
    def omitted(*args):
        result = original(*args)
        with wallet._source.wallet._db() as db:db.execute('DELETE FROM fills WHERE intent_id=?',(result['fill']['intent_id'],))
        return result
    monkeypatch.setattr(wallet._source.wallet,'execute',omitted)
    fill(wallet,clock,'loss','Sell',price='98')
    seal = finish(wallet,clock)
    with pytest.raises(ValueError,match='fill'):audit(wallet,seal,replay)


def test_source_consistent_sale_cannot_consume_an_unobserved_buy(tmp_path,monkeypatch):
    wallet,clock,replay = setup(tmp_path)
    original = wallet._source.wallet.execute
    def unowned(*args):
        with wallet._source.wallet._db() as db:
            db.execute('INSERT INTO lots VALUES (?,?,?,?,?,?)',('unobserved-buy','AAA/USDT',clock.now.isoformat(),'.06','6','.0108'))
        return original(*args)
    monkeypatch.setattr(wallet._source.wallet,'execute',unowned)
    fill(wallet,clock,'impossible-sale','Sell')
    seal = finish(wallet,clock)
    assert audit_trace(wallet,seal)['source_checkpoint_trace_pass']
    with pytest.raises(ValueError,match='independent'):audit(wallet,seal,replay)


def test_same_clock_fifo_uses_original_fill_sequence_instead_of_intent_name(tmp_path):
    wallet,clock,replay = setup(tmp_path,lifecycle=lifecycle(maximum_operations_per_poll=16))
    for identity,side in [('z-first','Buy'),('sell-one','Sell'),('a-second','Buy'),('sell-two','Sell')]:
        wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now)
    clock.advance(2);quote,rule = raw_market(clock)
    wallet.execute('z-first',quote,rule);wallet.execute('sell-one',quote,rule)
    wallet.mark({quote['pair']:quote},{rule['pair']:rule})
    wallet.execute('a-second',quote,rule);wallet.execute('sell-two',quote,rule)
    seal = finish(wallet,clock)
    assert audit_trace(wallet,seal)['source_checkpoint_trace_pass']
    # Native SQL orders equal opened_at by id, putting a-second ahead of the
    # actual earlier residual z-first. A replay claiming FIFO must reject that.
    with pytest.raises(ValueError,match='independent'):audit(wallet,seal,replay)


def test_decimal_purchase_cannot_exceed_stake_or_make_cash_negative(tmp_path):
    wallet,clock,replay = setup(tmp_path,config=config(capital=D(6),slippage=D(0)))
    result = fill(wallet,clock,'precision','Buy',price='17',step='1e-28')
    assert result['status'] == 'filled' and D(result['fill']['cost']) > D(6)
    seal = finish(wallet,clock)
    assert audit_trace(wallet,seal)['source_checkpoint_trace_pass']
    with pytest.raises(ValueError,match='stake|cash conservation'):audit(wallet,seal,replay)


def test_combined_preregistration_resource_floor_preserves_capture_budget(tmp_path,monkeypatch):
    wallet,clock = setup_capture(tmp_path,lifecycle=lifecycle(minimum_available_memory_bytes=1024))
    original = streaming.measure_resources
    monkeypatch.setattr(streaming,'measure_resources',lambda path:{**original(path),'available_memory_bytes':1})
    with pytest.raises(ValueError,match='combined'):
        register_replay(tmp_path/'replay',capture_root=wallet.root,expected_registration_sha256=wallet.registration_sha256,
            policy=policy(),clock=lambda:START-timedelta(seconds=1))
    assert not (tmp_path/'replay').exists()


@pytest.mark.parametrize('changes',[
    dict(maximum_scratch_bytes=131073),dict(maximum_scratch_bytes=2**31),dict(maximum_state_rows=0),
    dict(maximum_active_rows=15),dict(maximum_active_bytes=16384),dict(maximum_wall_seconds=0),
    dict(minimum_free_disk_bytes=1),dict(maximum_state_rows=True),
])
def test_invalid_or_unbounded_policy_is_rejected(changes):
    with pytest.raises(ValueError):policy(**changes)


def test_more_than_10000_marks_use_bounded_active_state_and_scratch(tmp_path):
    from cryptoforge.evidence_segments import canonical,parse
    p = policy(maximum_active_rows=16)
    wallet,clock,_ = setup(tmp_path)
    protocol = json.loads(json.dumps(wallet.protocol))
    protocol['end'] = (START+timedelta(seconds=10006)).isoformat()
    index = streaming._Scratch(tmp_path/'stress.sqlite',p)
    replayed = streaming._Replay(protocol,wallet.registration['native_manifest_sha256'],index,p,lifecycle())
    summary = parse(canonical(replayed.summary))
    _adjust = streaming._adjust
    tracemalloc.start();started = time.monotonic()
    try:
        for n in range(10005):
            at = (START+timedelta(seconds=n)).isoformat()
            result = dict(mode='paper',observed_at=at,cash='100',equity='100',gross_bid_equity='100',
                missing_mark_pairs=[],uncertain_liquidation_pairs=[],nontradable_small_basis_pairs=[],
                valuation='conditional_top_book_liquidation_after_fee_slip_dust_zero_assumption',live_eligible=False)
            changes = []
            if n == 0:
                row = ['day_anchor:'+START.date().isoformat(),'100']
                changes.append(dict(source='wallet.day_anchors',key=row[0],before=None,after=row));_adjust(summary,'wallet.day_anchors',row,1)
            row = [n+1,at,json.dumps(result,sort_keys=True)]
            changes.insert(0,dict(source='wallet.marks',key=n+1,before=None,after=row));_adjust(summary,'wallet.marks',row,1)
            prepared = dict(operation='mark',at=at,inputs=dict(quotes={},filters={}))
            complete = dict(at=at,result=result,changes=changes,after=dict(sources=parse(canonical(summary))))
            replayed.coverage.invalidate(at);replayed.operation(prepared,complete)
        peak = tracemalloc.get_traced_memory()[1]
        assert replayed.marks == 10005 and index.count == 10009
        assert replayed.peak_active_rows == 1 and replayed.peak_active_bytes < 2048
        assert peak < 2*1024*1024 and index.path.stat().st_size < p.maximum_scratch_bytes
        (tmp_path/'measurement.json').write_text(json.dumps(dict(marks=10005,scratch_rows=index.count,
            scratch_bytes=index.path.stat().st_size,peak_active_bytes=replayed.peak_active_bytes,
            python_peak_bytes=peak,seconds=time.monotonic()-started,
            scope='synthetic_replay_core_only_not_source_capture_process_RSS_or_full_runner'))+'\n')
    finally:
        tracemalloc.stop();index.db.close()
