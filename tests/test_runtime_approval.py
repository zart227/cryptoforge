from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.order_submission_journal import JournaledOrderClient, OrderSubmissionJournal
from cryptoforge.runtime_approval import (PinnedActiveModelRegistry, RuntimeApprovedOrderClient,
    approval_blockers, canonical, runtime_contract, sha)


NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
MODEL_SHA = 'a'*64
BUY = dict(symbol='HYPEUSDT', side='Buy', qty=Decimal('6'), order_link_id='test')


def configuration(tmp_path):
    policy = tmp_path/'policy.json'; policy.write_text('{}')
    args = SimpleNamespace(stake_amount='6', max_daily_loss='2', stop_loss_percent='.04',
        max_dust_fraction='.01', ml_threshold=.55, ml_max_age_hours=36, timeout=15,
        max_portfolio_drawdown=Decimal('.10'), max_open_positions=2, night_research_limit=12,
        exit_data_fallback=True, submission_risk_guard=True, spot_reservation_guard=True,
        local_order_reservations=True, settle_closed_reservations=False, live=True,
        use_night_research=True, append_fallback_pairs=True, allow_intraday_reversion=True,
        allow_emerging_momentum=False, ml_mode='gate', entry_model_sha256=MODEL_SHA,
        pair=['HYPE/USDT'], order_submission_journal=tmp_path/'orders.sqlite',
        decision_outbox=tmp_path/'decisions.sqlite', execution_controls=tmp_path/'controls.json',
        drawdown_state=tmp_path/'peak.json', fractional_risk_policy=policy,
        entry_runtime_approval=tmp_path/'approval.json')
    client = SimpleNamespace(api_key='synthetic-private-key-never-use', base_url='https://fake.invalid')
    launcher = tmp_path/'launcher.py'; launcher.write_text('# isolated synthetic launcher')
    policy_sha = sha(policy.read_bytes())
    provider = lambda: runtime_contract(args, client, launcher_path=launcher,
        fractional_policy_sha256=policy_sha, machine_id='fake-host')
    return args, client, provider, launcher


def write_approval(path, contract, **changes):
    value = dict(schema_version='executor-runtime-approval-v1', approved=True,
        runtime_sha256=sha(canonical(contract)), valid_from=NOW.isoformat(),
        valid_until=(NOW+timedelta(hours=1)).isoformat(), review_reference='synthetic-test-only')
    value.update(changes); path.write_text(json.dumps(value))


def guard_case(tmp_path):
    args, client, provider, launcher = configuration(tmp_path)
    write_approval(args.entry_runtime_approval, provider())
    sent = []
    client.create_spot_market_order = lambda **kw: sent.append(kw) or dict(retCode=0,result=dict(orderId='fake'))
    guard = RuntimeApprovedOrderClient(client, approval_path=args.entry_runtime_approval,
        contract_provider=provider, model_input_provider=lambda: dict(pair='HYPE/USDT',artifact_sha256=MODEL_SHA),
        clock=lambda: NOW)
    return args, provider, launcher, guard, sent


def test_contract_contains_explicit_limits_paths_source_hashes_but_no_raw_key(tmp_path):
    args, client, provider, _ = configuration(tmp_path)
    contract = provider()
    assert client.api_key not in canonical(contract).decode()
    assert contract['ownership']['account_uid_verified'] is False
    assert contract['configuration']['entry_model_sha256'] == MODEL_SHA
    assert contract['paths']['order_submission_journal'] == str(args.order_submission_journal.resolve())
    assert 'supabase_executor' in contract['implementation_sha256']
    assert sha(canonical(contract)) == sha(canonical(provider()))


@pytest.mark.parametrize('field,value', [('stake_amount','7'), ('max_open_positions',3),
    ('ml_threshold',.7), ('entry_model_sha256','b'*64), ('pair',['BTC/USDT']),
    ('order_submission_journal',Path('/tmp/different-orders.sqlite'))])
def test_contract_changes_cannot_reuse_prior_approval(tmp_path, field, value):
    args, _, provider, _ = configuration(tmp_path)
    write_approval(args.entry_runtime_approval, provider())
    setattr(args, field, value)
    assert approval_blockers(args.entry_runtime_approval, provider(), now=NOW)


@pytest.mark.parametrize('change', ['credential', 'host_endpoint', 'source', 'policy'])
def test_identity_and_original_source_changes_invalidate_binding(tmp_path, change):
    args, client, provider, launcher = configuration(tmp_path)
    write_approval(args.entry_runtime_approval, provider())
    if change == 'credential': client.api_key = 'other-synthetic-key'
    if change == 'host_endpoint': client.base_url = 'https://another-fake.invalid'
    if change == 'source': launcher.write_text('# modified')
    if change == 'policy':
        args.fractional_risk_policy.write_text('{"modified":true}')
        with pytest.raises(ValueError, match='changed after loading'): provider()
        return
    assert approval_blockers(args.entry_runtime_approval, provider(), now=NOW)


@pytest.mark.parametrize('raw', [None, '{', 'null', '[]', '{}',
    '{"schema_version":"executor-runtime-approval-v1","approved":true,"approved":false}',
])
def test_missing_or_corrupt_approval_never_allows_entry(tmp_path, raw):
    args, _, provider, _ = configuration(tmp_path)
    if raw is not None: args.entry_runtime_approval.write_text(raw)
    assert approval_blockers(args.entry_runtime_approval, provider(), now=NOW)


@pytest.mark.parametrize('changes', [dict(approved=False), dict(approved=1),
    dict(valid_until=NOW.isoformat()), dict(valid_from=(NOW+timedelta(seconds=1)).isoformat()),
    dict(valid_until=(NOW+timedelta(hours=25)).isoformat()), dict(review_reference=''),
    dict(valid_from='2026-10-16T12:00:00'), dict(extra=True)])
def test_denial_expiry_future_naive_and_wrong_schema_block(tmp_path, changes):
    args, _, provider, _ = configuration(tmp_path)
    write_approval(args.entry_runtime_approval, provider(), **changes)
    assert approval_blockers(args.entry_runtime_approval, provider(), now=NOW)


def test_each_submit_rereads_approval_and_sell_survives_denial(tmp_path):
    args, provider, _, guard, sent = guard_case(tmp_path)
    guard.create_spot_market_order(**BUY)
    write_approval(args.entry_runtime_approval, provider(), approved=False)
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    guard.contract_provider = lambda: pytest.fail('Sell queried entry binding')
    guard.create_spot_market_order(**dict(BUY,side='Sell'))
    assert [row['side'] for row in sent] == ['Buy','Sell']


def test_revocation_after_intent_commit_is_known_local_block(tmp_path, monkeypatch):
    args, provider, _, guard, sent = guard_case(tmp_path)
    journal = OrderSubmissionJournal(args.order_submission_journal)
    prepare = journal.prepare
    def revoked(**intent):
        result = prepare(**intent)
        write_approval(args.entry_runtime_approval, provider(), approved=False)
        return result
    monkeypatch.setattr(journal, 'prepare', revoked)
    with pytest.raises(OrderControlBlocked): JournaledOrderClient(guard, journal).create_spot_market_order(**BUY)
    with sqlite3.connect(journal.path) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'blocked'
    assert sent == []


def test_source_change_cannot_be_adopted_by_reapproval_mid_cycle(tmp_path):
    args, provider, launcher, guard, sent = guard_case(tmp_path)
    launcher.write_text('# runtime source modified after import')
    write_approval(args.entry_runtime_approval, provider())
    with pytest.raises(OrderControlBlocked, match='changed during cycle'): guard.create_spot_market_order(**BUY)
    assert sent == []


def test_clock_expiry_and_backwards_movement_block(tmp_path):
    _, _, _, guard, sent = guard_case(tmp_path)
    guard.clock = lambda: NOW+timedelta(hours=1)
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    guard.clock = lambda: NOW-timedelta(seconds=1)
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    assert sent == []


def test_expiry_during_contract_validation_does_not_use_earlier_time(tmp_path):
    _, provider, _, guard, sent = guard_case(tmp_path)
    current = [NOW]
    guard.clock = lambda: current[0]
    def slow_contract():
        current[0] = NOW+timedelta(hours=1)
        return provider()
    guard.contract_provider = slow_contract
    with pytest.raises(OrderControlBlocked, match='expired'): guard.create_spot_market_order(**BUY)
    assert sent == []


@pytest.mark.parametrize('model_input', [None, {}, dict(pair='BTC/USDT',artifact_sha256=MODEL_SHA),
    dict(pair='HYPE/USDT',artifact_sha256='b'*64)])
def test_order_requires_exact_pinned_model_input_for_same_symbol(tmp_path, model_input):
    _, _, _, guard, sent = guard_case(tmp_path)
    guard.model_input_provider = lambda: model_input
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    assert sent == []


def test_limit_buy_cannot_bypass_approval(tmp_path):
    _, _, _, guard, sent = guard_case(tmp_path)
    with pytest.raises(OrderControlBlocked): guard.create_spot_limit_order(**BUY)
    assert sent == []


@pytest.mark.parametrize('model', [None, SimpleNamespace(artifact_sha256='b'*64)])
def test_registry_does_not_silently_adopt_another_model(model):
    registry = PinnedActiveModelRegistry(SimpleNamespace(latest=lambda **kw: model),MODEL_SHA)
    with pytest.raises(ValueError): registry.latest()


def test_actual_executor_uses_pinned_model_before_one_fake_buy(tmp_path):
    from test_exit_data_fallback import setup_case
    args, provider, _, guard, _ = guard_case(tmp_path)
    executor, _, now, sent = setup_case('healthy', holding=False)
    executor.entry_blockers = ()
    executor.bybit.get_unified_usdt_balance = lambda: SimpleNamespace(usdt_wallet_balance=Decimal('100'))
    model = SimpleNamespace(artifact_sha256=MODEL_SHA, feature_version='candle-v1', model_version='fake',
        predict_probability=lambda features: .99)
    executor.active_model_registry = PinnedActiveModelRegistry(SimpleNamespace(latest=lambda **kw:model), MODEL_SHA)
    executor.ml_mode = 'gate'
    guard.client = executor.bybit
    guard.model_input_provider = lambda: executor._last_model_input
    executor.bybit = guard
    assert executor.run_once('HYPE/USDT', live=True, now=now).decision == 'approve_entry'
    assert len(sent) == 1 and sent[0]['side'] == 'Buy'
    model.artifact_sha256 = 'b'*64
    assert executor.run_once('HYPE/USDT', live=True, now=now).decision == 'reject_entry'
    assert len(sent) == 1


def test_launcher_guard_with_missing_approval_keeps_existing_stop(tmp_path, monkeypatch):
    from test_executor_outage_cycle import harness
    from scripts import run_supabase_live_executor as launcher
    args, bybit, sent = harness(tmp_path, monkeypatch)
    args.entry_runtime_approval = tmp_path/'missing-approval.json'
    args.entry_model_sha256 = MODEL_SHA
    args.entry_account_policy = tmp_path/'missing-account-policy.json'
    args.ml_mode = 'gate'
    assert launcher.run_cycle(args, bybit) == 1
    assert len(sent) == 1 and sent[0]['side'] == 'Sell'
    risk = json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert risk['configured_protections']['runtime_approval'] is True
    assert risk['configured_protections']['entry_account_verification'] is True
    assert any('runtime binding unavailable' in reason for reason in risk['entry_blockers'])


@pytest.mark.parametrize('arguments', [
    ['--entry-runtime-approval','approval.json'],
    ['--entry-model-sha256',MODEL_SHA],
    ['--entry-account-policy','account-policy.json'],
])
def test_cli_rejects_incomplete_guard_configuration_before_credentials(monkeypatch, arguments):
    from scripts import run_supabase_live_executor as launcher
    monkeypatch.setattr('sys.argv',['executor',*arguments])
    monkeypatch.setattr(launcher.BybitPrivateClient, 'from_env',
        lambda: pytest.fail('incomplete runtime approval reached credentials'))
    with pytest.raises(SystemExit) as result: launcher.main()
    assert result.value.code == 2


@pytest.mark.parametrize('revoke_during_risk', [False, True])
@pytest.mark.parametrize('key_policy', [None,'match','changed_after_start'])
def test_full_launcher_buy_path_rechecks_approval_after_risk_queries(tmp_path, monkeypatch, revoke_during_risk,key_policy):
    from test_executor_outage_cycle import harness
    from scripts import run_supabase_live_executor as launcher
    from cryptoforge.supabase_executor import CandleRow
    from cryptoforge.execution_ownership import credential_scope
    args, bybit, sent = harness(tmp_path, monkeypatch, holding=False)
    bybit.api_key = 'fake-key'; bybit.base_url = 'https://fake.invalid'
    now = datetime.now(UTC)
    args.entry_runtime_approval = tmp_path/'approval.json'
    args.entry_model_sha256 = MODEL_SHA
    args.ml_mode = 'gate'
    args.spot_reservation_guard = True
    args.drawdown_state = tmp_path/'peak.json'
    args.max_portfolio_drawdown = Decimal('.10')
    args.fractional_risk_policy = tmp_path/'policy.json'
    args.fractional_risk_policy.write_text(json.dumps(dict(schema_version='fractional-entry-risk-v1',
        maximum_position_fraction='.05', maximum_planned_risk_fraction='.005', round_trip_cost_fraction='.002')))
    if key_policy:
        from test_account_verification import write_policy
        args.entry_account_policy=tmp_path/'account-policy.json'
        write_policy(args.entry_account_policy)
    args.execution_controls.write_text(json.dumps(dict(schema_version='executor-controls-v1',
        no_new_entry=False, kill_switch=False)))
    args.drawdown_state.write_text(json.dumps(dict(schema_version='observed-portfolio-drawdown-v1',
        owner_id=sha(json.dumps(credential_scope(bybit),sort_keys=True).encode()), maximum_drawdown='.10',
        peak_equity='200', last_equity='200', observed_at=now.isoformat(), breach_latched=False)))
    bybit.get_unified_wallet_coins = lambda: [dict(coin='USDT',usdValue='100',walletBalance='100',
        locked='0',bonus='0',borrowAmount='0',spotBorrow='0',totalOrderIM='0',totalPositionIM='0')]
    calls = [];identity_calls=[]
    def risk_page(*a, **kw):
        if a[0]=='/v5/user/query-api':
            from test_account_verification import key_response
            identity_calls.append('query-api')
            response=key_response(api_key=bybit.api_key,now=datetime.now(UTC))
            if key_policy=='changed_after_start' and calls:
                response['result']['permissions']['Wallet']=['Withdraw']
            return response
        calls.append('reservation-risk-query')
        if revoke_during_risk:
            value = json.loads(args.entry_runtime_approval.read_bytes())
            value['approved'] = False
            args.entry_runtime_approval.write_text(json.dumps(value))
        return dict(retCode=0,result=dict(category='spot',list=[],nextPageCursor=''))
    bybit._private_get = risk_page
    monkeypatch.setattr(launcher, 'reconcile_journal', lambda *a: True)
    monkeypatch.setattr(launcher, 'NightResearchSelector', lambda *a: SimpleNamespace(select_pairs=lambda **kw:
        SimpleNamespace(pairs=['HYPE/USDT'],source='night_research',reasons=(),generated_at=now)))
    rows = launcher.BybitPublicClient().get_klines()
    candles = [CandleRow(pair='HYPE/USDT',symbol=r.symbol,
        open_time=datetime.fromtimestamp(r.start_ms/1000,UTC),open=r.open,high=r.high,
        low=r.low,close=r.close,volume=r.volume) for r in rows]
    monkeypatch.setattr(launcher, 'SupabaseMarketReader', lambda *a: SimpleNamespace(read_candles=lambda *a,**kw:candles))
    model = SimpleNamespace(artifact_sha256=MODEL_SHA, feature_version='candle-v1',model_version='fake',
        predict_probability=lambda features:.99)
    monkeypatch.setattr(launcher, 'ActiveModelRegistry', lambda *a: SimpleNamespace(latest=lambda **kw:model))
    contract = runtime_contract(args, bybit, launcher_path=launcher.__file__,
        fractional_policy_sha256=sha(args.fractional_risk_policy.read_bytes()),
        account_policy_sha256=sha(args.entry_account_policy.read_bytes()) if key_policy else None)
    write_approval(args.entry_runtime_approval, contract, valid_from=(now-timedelta(minutes=1)).isoformat(),
        valid_until=(now+timedelta(minutes=5)).isoformat())
    blocked=revoke_during_risk or key_policy=='changed_after_start'
    assert launcher.run_cycle(args,bybit) == (1 if blocked else 0)
    assert calls == ['reservation-risk-query']
    assert len(identity_calls)==(2 if key_policy else 0)
    with sqlite3.connect(args.order_submission_journal) as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == (
            'blocked' if blocked else 'acknowledged')
    if blocked:
        assert sent == []
    else:
        assert len(sent)==1 and sent[0]['side']=='Buy'
