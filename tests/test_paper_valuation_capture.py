from copy import deepcopy
from datetime import timedelta
from decimal import localcontext
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

import cryptoforge.paper_valuation_capture as capture
from cryptoforge.paper_valuation_capture import (
    CapturedPaperWallet, audit_valuation_capture, canonical, digest, observe_valuation_market,
)
from test_paper_wallet import Clock, START, config, market


def setup(tmp_path, **kwargs):
    clock = Clock()
    clock.now = START-timedelta(seconds=10)
    wallet = CapturedPaperWallet.create(tmp_path/'new-study', candidate_sha='a'*64,
        config=config(), start=START, end=START+timedelta(hours=1), clock=clock, **kwargs)
    clock.now = START
    return wallet, clock


def raw_market(clock, pair='AAA/USDT', price='100', **changes):
    quote, rule = market(clock, pair, price=price, **changes)
    instrument = dict(retCode=0, result=dict(list=[dict(symbol=pair.replace('/', ''),
        quoteCoin='USDT', status='Trading', lotSizeFilter=dict(basePrecision=rule['quantity_step'],
            minOrderAmt=rule['minimum_notional'], maxMarketOrderQty=rule['maximum_market_quantity']))]))
    millis = int(clock.now.timestamp()*1000)
    book = dict(retCode=0, time=millis, result=dict(s=pair.replace('/', ''), ts=millis,
        b=[[price, quote['bid_qty']]], a=[[price, quote['ask_qty']]], u=123))

    class Public:
        base_url = 'https://api.bybit.com'
        calls = []

        def _get_json(self, path, query):
            self.calls.append((path, query))
            return book if 'orderbook' in path else instrument

    public = Public()
    result = observe_valuation_market(public, pair, clock=clock)
    assert len(public.calls) == 2
    assert all(query['category'] == 'spot' for _, query in public.calls)
    return result


def mark(wallet, clock, *, raw=True, **kwargs):
    q, r = (raw_market if raw else market)(clock, **kwargs)
    return wallet.mark({q['pair']: q}, {r['pair']: r})


def fill(wallet, clock, intent, side, *, raw=True, **kwargs):
    wallet.enqueue(intent, kwargs.get('pair', 'AAA/USDT'), side, created_at=clock.now)
    clock.advance()
    return wallet.execute(intent, *(raw_market if raw else market)(clock, **kwargs))


def audit(wallet):
    return audit_valuation_capture(wallet.root, expected_protocol_sha256=wallet.protocol_sha256,
        clock=lambda: START+timedelta(hours=1))


def events(wallet):
    with sqlite3.connect(wallet.root/'events.sqlite') as db:
        return db.execute('SELECT * FROM events ORDER BY seq').fetchall()


def rewrite_chain(wallet, change):
    """Adversary recomputes chain hashes; source replay must still reject it."""
    rows = events(wallet)
    previous = wallet.protocol_sha256
    with sqlite3.connect(wallet.root/'events.sqlite') as db:
        for seq, kind, raw, _, _ in rows:
            payload = json.loads(raw)
            change(seq, kind, payload)
            sha = digest(canonical(dict(seq=seq, kind=kind, payload=payload, previous=previous)))
            db.execute('UPDATE events SET payload=?,previous=?,sha=? WHERE seq=?',
                (canonical(payload).decode(), previous, sha, seq))
            previous = sha


def test_same_clock_prefill_postfill_marks_replay_by_actual_sequence(tmp_path):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    fill(wallet, clock, 'z-buy', 'Buy')
    # Both marks and the fill use one timestamp; lexical intent sorting is irrelevant.
    mark(wallet, clock)
    mark(wallet, clock, price='98')
    fill(wallet, clock, 'a-sell', 'Sell', price='98')
    mark(wallet, clock, price='98')
    report = audit(wallet)
    assert report['mark_source_evidence_pass']
    assert report['marks_checked'] == report['raw_source_marks'] == 4
    assert report['fills_checked'] == 2
    assert not report['live_admission_granted']
    assert not report['economic_profitability_established']


def test_worker_runs_with_adapter_without_changing_frozen_worker(tmp_path):
    from cryptoforge.paper_worker import PaperWorker
    wallet, clock = setup(tmp_path)
    worker = PaperWorker(wallet, tmp_path/'worker.sqlite', policy=dict(enabled=True, status='frozen',
        runtime=dict(maximum_new_signals_per_tick=2, wall_budget_seconds=10),
        exits=dict(stop_fraction='.04', maximum_hold_seconds=3600)),
        market=lambda pair: raw_market(clock, pair), clock=clock)
    prediction = dict(candidate_sha256='a'*64, opportunity='new', predicted_at=clock.now.isoformat(),
        observed_at=clock.now.isoformat(), would_enter=True, pair='AAA/USDT')
    worker.tick([prediction], window_start=START, window_end=START+timedelta(hours=1))
    clock.advance()
    worker.tick([], window_start=START, window_end=START+timedelta(hours=1))
    assert audit(wallet)['fills_checked'] == 1


def test_multiple_fills_with_one_timestamp_use_capture_order_not_names(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.enqueue('z-first', 'AAA/USDT', 'Buy', created_at=clock.now)
    wallet.enqueue('a-second', 'BBB/USDT', 'Buy', created_at=clock.now)
    clock.advance()
    assert wallet.execute('z-first', *raw_market(clock))['status'] == 'filled'
    mark(wallet, clock)
    assert wallet.execute('a-second', *raw_market(clock, 'BBB/USDT'))['status'] == 'filled'
    q1, r1 = raw_market(clock)
    q2, r2 = raw_market(clock, 'BBB/USDT')
    wallet.mark({'AAA/USDT': q1, 'BBB/USDT': q2}, {'AAA/USDT': r1, 'BBB/USDT': r2})
    assert len({row['filled_at'] for row in wallet.snapshot()['fills']}) == 1
    assert audit(wallet)['fills_checked'] == 2


def test_normalized_quotes_without_full_raw_sources_never_qualify(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy', raw=False)
    mark(wallet, clock, raw=False)
    report = audit(wallet)
    assert report['known_valuation_marks'] == 1
    assert report['raw_source_marks'] == 0
    assert not report['mark_source_evidence_pass']


@pytest.mark.parametrize('problem', ['missing_quote', 'stale_quote', 'stale_rules', 'low_depth', 'missing_rules'])
def test_unknown_liquidation_is_preserved_not_a_numeric_pass(tmp_path, problem):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    q, r = raw_market(clock)
    quotes, rules = {'AAA/USDT': q}, {'AAA/USDT': r}
    if problem == 'missing_quote': quotes = {}
    if problem == 'stale_quote': q['observed_at'] = (clock.now-timedelta(seconds=11)).isoformat()
    if problem == 'stale_rules':
        clock.advance(301)
        quotes = {'AAA/USDT': raw_market(clock)[0]}
        rules = {}  # Keep the original, now stale cached rule; never rewrite it.
    if problem == 'low_depth': q['bid_qty'] = '.000001'
    if problem == 'missing_rules':
        # No cached rules either: an unfilled unknown market cannot get current defaults.
        with wallet._db() as db: db.execute('DELETE FROM market_cache')
        # This bypass must fail before it can create a qualified record.
        with pytest.raises(ValueError, match='uncaptured'):
            wallet.mark(quotes, {})
        return
    result = wallet.mark(quotes, rules)
    assert result['equity'] is None
    assert not audit(wallet)['mark_source_evidence_pass']


def test_cached_filter_sources_are_retained_for_later_mark(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    quote, _ = raw_market(clock)
    wallet.mark({'AAA/USDT': quote})
    assert audit(wallet)['mark_source_evidence_pass']


def test_raw_book_or_instrument_drift_cannot_be_silently_qualified(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    clock.advance()
    q, r = raw_market(clock)
    r['raw_response']['result']['list'][0]['lotSizeFilter']['basePrecision'] = '.01'
    wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    assert not audit(wallet)['mark_source_evidence_pass']


def test_restart_and_duplicate_fill_keep_original_sequence(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    restored = CapturedPaperWallet.resume(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    result = restored.execute('buy', *raw_market(clock))
    assert result['duplicate']
    mark(restored, clock)
    assert audit(restored)['fills_checked'] == 1


def test_native_failure_retains_prepared_record_and_blocks_restart(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.enqueue('buy', 'AAA/USDT', 'Buy', created_at=clock.now)
    clock.advance()
    q, r = raw_market(clock)
    q['bid'] = '200'
    with pytest.raises(ValueError): wallet.execute('buy', q, r)
    assert events(wallet)[-1][1] == 'prepared'
    with pytest.raises(ValueError, match='unfinished'):
        CapturedPaperWallet.resume(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    with pytest.raises(ValueError, match='unfinished'): audit(wallet)


def test_failed_completion_never_allows_automatic_resubmit(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    original = wallet._append
    def fail(kind, payload):
        if kind == 'complete': raise OSError('disk unavailable')
        return original(kind, payload)
    monkeypatch.setattr(wallet, '_append', fail)
    with pytest.raises(OSError): fill(wallet, clock, 'buy', 'Buy')
    assert len(wallet.snapshot()['fills']) == 1
    with pytest.raises(ValueError, match='unfinished'): wallet.execute('buy', *raw_market(clock))


@pytest.mark.parametrize('mutation', ['equity', 'cash', 'sequence', 'quote', 'unlogged_mark', 'event_hash'])
def test_tampering_or_uncaptured_writes_block_audit(tmp_path, mutation):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    mark(wallet, clock)
    if mutation == 'unlogged_mark':
        wallet._wallet.mark({'AAA/USDT': raw_market(clock)[0]})
    elif mutation == 'event_hash':
        with sqlite3.connect(wallet.root/'events.sqlite') as db:
            db.execute("UPDATE events SET sha=? WHERE seq=2", ('f'*64,))
    else:
        def change(seq, kind, event):
            if kind == 'complete' and 'equity' in event['result']:
                if mutation == 'equity': event['result']['equity'] = '999'
                if mutation == 'cash': event['after']['state']['cash'] = '999'
                if mutation == 'sequence': event['prepared_seq'] = 1
            if mutation == 'quote' and kind == 'prepared' and event['operation'] == 'mark':
                event['inputs']['quotes']['AAA/USDT']['bid'] = '101'
        rewrite_chain(wallet, change)
    with pytest.raises(ValueError): audit(wallet)


def test_event_limit_fails_before_mutating_wallet(tmp_path):
    wallet, clock = setup(tmp_path, max_events=3)
    mark(wallet, clock)
    before = wallet.snapshot()
    with pytest.raises(ValueError, match='budget'): mark(wallet, clock)
    assert wallet.snapshot() == before


def test_local_operation_lease_prevents_parallel_writer(tmp_path):
    wallet, clock = setup(tmp_path)
    with wallet._lock():
        with pytest.raises(BlockingIOError): mark(wallet, clock)
    assert len(events(wallet)) == 1


@pytest.mark.parametrize('problem', ['existing', 'backdated', 'symlink', 'bad_candidate'])
def test_legacy_or_backdated_namespace_cannot_be_adopted(tmp_path, problem):
    clock = Clock()
    root = tmp_path/'isolated'
    start = START+timedelta(seconds=10)
    candidate = 'a'*64
    if problem == 'existing': root.mkdir()
    if problem == 'backdated': start = START
    if problem == 'symlink':
        (tmp_path/'other').mkdir()
        root.symlink_to(tmp_path/'other', target_is_directory=True)
    if problem == 'bad_candidate': candidate = 'legacy'
    with pytest.raises((ValueError, FileExistsError)):
        CapturedPaperWallet.create(root, candidate_sha=candidate, config=config(), start=start,
            end=START+timedelta(hours=1), clock=clock)


def test_sealed_audit_does_not_read_reward_bearing_databases(tmp_path):
    wallet, clock = setup(tmp_path)
    (wallet.root/'events.sqlite').unlink()
    (wallet.root/'wallet.sqlite').unlink()
    result = audit_valuation_capture(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    assert result['status'] == 'sealed_until_capture_end'
    assert result['performance_hidden']
    assert not result['live_admission_granted']


def test_sources_are_read_only_for_audit_and_wrong_pin_fails(tmp_path):
    wallet, clock = setup(tmp_path)
    fill(wallet, clock, 'buy', 'Buy')
    mark(wallet, clock)
    before = {p.name: p.read_bytes() for p in wallet.root.iterdir()}
    assert audit(wallet)['mark_source_evidence_pass']
    assert {p.name: p.read_bytes() for p in wallet.root.iterdir()} == before
    with pytest.raises(ValueError, match='pin'):
        audit_valuation_capture(wallet.root, expected_protocol_sha256='0'*64, clock=clock)


def test_runtime_drift_and_missing_wallet_cannot_reinitialize_state(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    hashes = capture.runtime_hashes()
    monkeypatch.setattr(capture, 'runtime_hashes', lambda: {**hashes, 'different': 'f'*64})
    with pytest.raises(ValueError, match='runtime drift'): mark(wallet, clock)
    monkeypatch.undo()
    wallet.path.unlink()
    with pytest.raises(FileNotFoundError):
        CapturedPaperWallet.resume(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    assert not wallet.path.exists()


def test_credentials_rejected_before_writing_capture(tmp_path):
    wallet, clock = setup(tmp_path)
    q, r = raw_market(clock)
    q['api_key'] = 'never-write-this'
    with pytest.raises(ValueError, match='credentials'): wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    assert len(events(wallet)) == 1
    assert b'never-write-this' not in (wallet.root/'events.sqlite').read_bytes()


def test_unstructured_notes_and_precision_drift_block_before_operation(tmp_path):
    wallet, clock = setup(tmp_path)
    q, r = raw_market(clock)
    q['notes'] = 'not a market field'
    with pytest.raises(ValueError, match='allowlisted'): wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    with localcontext() as context:
        context.prec = 12
        with pytest.raises(ValueError, match='Decimal'): mark(wallet, clock)
    assert len(events(wallet)) == 1


def test_wallet_source_changed_during_replay_is_rejected(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    original = capture.verify_paper_fill_arithmetic
    def alter(*args):
        result = original(*args)
        # An atomic pathname replacement can evade locks held on the old inode.
        replacement = tmp_path/'replacement.sqlite'
        replacement.write_bytes(wallet.path.read_bytes())
        with sqlite3.connect(replacement) as db:
            db.execute("UPDATE state SET value='100.0' WHERE key='cash'")
        replacement.replace(wallet.path)
        return result
    monkeypatch.setattr(capture, 'verify_paper_fill_arithmetic', alter)
    with pytest.raises(ValueError, match='source drift'): audit(wallet)


def test_public_adapter_rejects_other_origin_without_requests():
    class Unsafe:
        base_url = 'https://api.bybit.com.evil'
        def _get_json(self, *args): pytest.fail('network must not run')
    with pytest.raises(ValueError, match='origin'): observe_valuation_market(Unsafe(), 'AAA/USDT')


def test_cli_has_no_clock_override_and_protects_all_capture_sources(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('valuation_cli', Path('scripts/audit_paper_valuation.py'))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    wallet, clock = setup(tmp_path)
    mark(wallet, clock)
    args = ['--root', str(wallet.root), '--expected-protocol-sha256', wallet.protocol_sha256]
    assert cli.main(args) == 0
    assert not json.loads(capsys.readouterr().out)['live_admission_granted']
    assert cli.main(args+['--output', str(wallet.root/'protocol.json')]) == 1
    capsys.readouterr()
    output = tmp_path/'new-report.json'
    assert cli.main(args+['--output', str(output)]) == 0
    assert output.is_file()
    capsys.readouterr()
    assert cli.main(args+['--output', str(output)]) == 1
    with pytest.raises(SystemExit): cli.main(args+['--as-of', START.isoformat()])
