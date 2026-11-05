from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
import json
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from cryptoforge.account_ownership import account_execution_lease, AccountLeaseOrderClient
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.execution_ownership import execution_lease
from cryptoforge.order_submission_journal import OrderSubmissionJournal
from test_account_verification import key_response, write_policy


NOW=datetime(2026,10,16,12,tzinfo=UTC)


def client(key='fake-key-a'):
    calls=[];sent=[]
    def get(path,params):
        calls.append((path,params))
        return key_response(api_key=key,now=NOW)
    return SimpleNamespace(api_key=key,base_url='https://api.bybit.com',_private_get=get,
        calls=calls,sent=sent,create_spot_market_order=lambda **kw:sent.append(kw))


@contextmanager
def lease(root,*,bybit=None,journal=None,machine='fake-host'):
    policy=root/'policy.json'
    if not policy.exists():write_policy(policy)
    with account_execution_lease(journal or root/'orders.sqlite',bybit or client(),
            policy_path=policy,lock_directory=root/'locks',machine_id=machine,clock=lambda:NOW) as active:
        yield active


def test_verified_uid_binding_preserves_credential_record_and_restarts_without_query(tmp_path):
    bybit=client()
    with lease(tmp_path,bybit=bybit) as active:
        active.assert_held()
        journal=OrderSubmissionJournal(tmp_path/'orders.sqlite')
        journal.prepare(symbol='BTCUSDT',side='Buy',qty=Decimal('6'),order_link_id='original-unknown')
        assert active.diagnostic()['account_uid_verified_at_binding']
    original=(tmp_path/'orders.sqlite').read_bytes()
    assert bybit.calls==[('/v5/user/query-api',{})]
    bybit._private_get=lambda *a:pytest.fail('restart unnecessarily depends on key query')
    with lease(tmp_path,bybit=bybit):pass
    assert (tmp_path/'orders.sqlite').read_bytes()==original
    credential=json.loads((tmp_path/'orders.sqlite.owner.json').read_bytes())
    assert credential['account_uid_verified'] is False  # Historical schema unchanged.
    record=json.loads((tmp_path/'orders.sqlite.account-owner.json').read_bytes())
    assert record['account_uid_verified_at_binding'] is True
    raw=json.dumps(record)
    assert bybit.api_key not in raw and 'fake-host' not in raw and '"101"' not in raw
    assert (tmp_path/'orders.sqlite.account-owner.json').stat().st_mode & 0o777==0o600


def test_other_key_same_uid_cannot_start_second_journal_during_owner_or_after_restart(tmp_path):
    other=client('fake-key-b');second=tmp_path/'second.sqlite'
    with lease(tmp_path):
        with pytest.raises(ValueError,match='another local executor'):
            with lease(tmp_path,bybit=other,journal=second):pass
    with pytest.raises(ValueError,match='explicit recovery'):
        with lease(tmp_path,bybit=other,journal=second):pass
    assert not second.exists() and not other.calls


def test_same_key_cannot_switch_journal_after_uid_binding(tmp_path):
    with lease(tmp_path):pass
    with pytest.raises(ValueError):
        with lease(tmp_path,journal=tmp_path/'fresh.sqlite'):pass
    assert not (tmp_path/'fresh.sqlite').exists()


def test_unbound_and_credential_only_journals_are_not_adopted(tmp_path):
    path=tmp_path/'orders.sqlite'
    with execution_lease(path,client(),lock_directory=tmp_path/'locks',machine_id='fake-host'):pass
    original=path.read_bytes()
    with pytest.raises(ValueError,match='automatically'):
        with lease(tmp_path):pass
    assert path.read_bytes()==original
    assert not path.with_name(path.name+'.account-owner.json').exists()


@pytest.mark.parametrize('change',['host','endpoint','policy'])
def test_changed_binding_requires_explicit_recovery(tmp_path,change):
    bybit=client()
    with lease(tmp_path,bybit=bybit):pass
    if change=='endpoint':bybit.base_url='https://other-fake.invalid'
    if change=='policy':
        path=tmp_path/'policy.json';source=json.loads(path.read_bytes());source['expected_ips']=['192.0.2.2']
        path.write_text(json.dumps(source))
    with pytest.raises(ValueError):
        with lease(tmp_path,bybit=bybit,machine='other-host' if change=='host' else 'fake-host'):pass


def test_first_bootstrap_requires_fresh_authenticated_uid_before_journal_creation(tmp_path):
    bybit=client()
    def wrong(*a):
        value=key_response(api_key=bybit.api_key);value['result']['userID']=102
        return value
    bybit._private_get=wrong
    with pytest.raises(ValueError):
        with lease(tmp_path,bybit=bybit):pass
    assert not (tmp_path/'orders.sqlite').exists()
    assert not list((tmp_path/'locks/accounts').glob('*.owner.json'))


def test_bootstrap_query_failure_does_not_expose_upstream_credentials(tmp_path):
    import traceback
    bybit=client()
    def fail(*a):raise OSError('sensitive-upstream fake-key-a')
    bybit._private_get=fail
    with pytest.raises(ValueError) as error:
        with lease(tmp_path,bybit=bybit):pass
    assert 'sensitive-upstream' not in ''.join(traceback.format_exception(error.value))
    assert not (tmp_path/'orders.sqlite').exists()


def test_missing_journal_or_incomplete_account_sidecars_are_not_recreated(tmp_path):
    with lease(tmp_path):pass
    journal=tmp_path/'orders.sqlite';journal.unlink()
    with pytest.raises(ValueError,match='incomplete'):
        with lease(tmp_path):pass
    assert not journal.exists()


def test_partial_binding_write_failure_preserves_journal_and_requires_recovery(tmp_path,monkeypatch):
    from cryptoforge import account_ownership as module
    original_save=module.save_identity
    def partial(path,identity):
        if path.name.endswith('.account-owner.json'):raise OSError('injected failure')
        return original_save(path,identity)
    monkeypatch.setattr(module,'save_identity',partial)
    with pytest.raises(OSError):
        with lease(tmp_path):pass
    original=(tmp_path/'orders.sqlite').read_bytes()
    monkeypatch.setattr(module,'save_identity',original_save)
    with pytest.raises(ValueError,match='incomplete'):
        with lease(tmp_path):pass
    assert (tmp_path/'orders.sqlite').read_bytes()==original


def test_replaced_journal_is_not_accepted_even_with_identical_bytes(tmp_path):
    path=tmp_path/'orders.sqlite'
    with lease(tmp_path):pass
    replacement=tmp_path/'copy.sqlite';replacement.write_bytes(path.read_bytes());os.replace(replacement,path)
    with pytest.raises(ValueError,match='lineage'):
        with lease(tmp_path):pass


def test_escaped_order_client_cannot_submit_after_lease_ends(tmp_path):
    bybit=client()
    with lease(tmp_path,bybit=bybit) as active:
        guarded=AccountLeaseOrderClient(bybit,active)
        guarded.create_spot_market_order(side='Sell')
    for side in ('Buy','Sell'):
        with pytest.raises(OrderControlBlocked):guarded.create_spot_market_order(side=side)
    assert [v['side'] for v in bybit.sent]==['Sell']


@pytest.mark.parametrize('change',['account_record','credential_record','journal','lock_inode','credentials'])
def test_loss_of_live_ownership_blocks_both_new_buy_and_sell(tmp_path,change):
    bybit=client()
    with lease(tmp_path,bybit=bybit) as active:
        guarded=AccountLeaseOrderClient(bybit,active)
        if change=='account_record':(tmp_path/'orders.sqlite.account-owner.json').write_text('{}')
        if change=='credential_record':(tmp_path/'orders.sqlite.owner.json').write_text('{}')
        if change=='journal':(tmp_path/'orders.sqlite').unlink()
        if change=='lock_inode':
            copy=tmp_path/'new-lock';copy.write_bytes(b'');os.replace(copy,active.lock_path)
        if change=='credentials':bybit.api_key='other-key'
        for side in ('Buy','Sell'):
            with pytest.raises(OrderControlBlocked):guarded.create_spot_market_order(side=side)
        assert not bybit.sent


def hold_account_child(root,ready):
    with lease(Path(root)):
        ready.set()
        import time
        time.sleep(10)


def test_real_cross_key_process_contention_and_crash_restart_preserve_journal(tmp_path):
    write_policy(tmp_path/'policy.json')
    context=multiprocessing.get_context('spawn')
    ready=context.Event();process=context.Process(target=hold_account_child,args=(str(tmp_path),ready))
    process.start()
    try:
        assert ready.wait(5)
        original=(tmp_path/'orders.sqlite').read_bytes()
        with pytest.raises(ValueError,match='another local executor'):
            with lease(tmp_path,bybit=client('fake-key-b'),journal=tmp_path/'second.sqlite'):pass
        process.kill();process.join(5)
        assert not process.is_alive()
        with lease(tmp_path):pass
        assert (tmp_path/'orders.sqlite').read_bytes()==original
        assert not (tmp_path/'second.sqlite').exists()
    finally:
        if process.is_alive():process.kill()
        process.join(5)


def test_uid_mode_cannot_call_cycle_without_lease(tmp_path,monkeypatch):
    from scripts import run_supabase_live_executor as launcher
    monkeypatch.setattr(launcher.SupabaseRestClient,'from_env',lambda **kw:pytest.fail('cycle proceeded without ownership'))
    with pytest.raises(ValueError,match='active verified account lease'):
        launcher.run_cycle(SimpleNamespace(account_ownership_guard=True),client())


def test_cli_uid_guard_requires_account_policy_before_credentials(monkeypatch):
    from scripts import run_supabase_live_executor as launcher
    monkeypatch.setattr('sys.argv',['executor','--account-ownership-guard'])
    monkeypatch.setattr(launcher.BybitPrivateClient,'from_env',lambda:pytest.fail('unbound UID mode reached credentials'))
    with pytest.raises(SystemExit) as result:launcher.main()
    assert result.value.code==2


def test_actual_cycle_keeps_known_stop_on_key_info_outage_under_existing_uid_lease(tmp_path,monkeypatch):
    from test_executor_outage_cycle import harness,offline
    from scripts import run_supabase_live_executor as launcher
    args,bybit,sent=harness(tmp_path,monkeypatch)
    bybit.api_key='fake-key-a';bybit.base_url='https://api.bybit.com'
    now=datetime.now(UTC)
    bybit._private_get=lambda *a:key_response(api_key=bybit.api_key,now=now)
    args.account_ownership_guard=True
    args.entry_account_policy=tmp_path/'policy.json';write_policy(args.entry_account_policy)
    args.entry_runtime_approval=tmp_path/'missing-approval.json'
    args.entry_model_sha256='a'*64;args.ml_mode='gate'
    with account_execution_lease(args.order_submission_journal,bybit,policy_path=args.entry_account_policy,
            lock_directory=tmp_path/'.local/state/executor-ownership',clock=lambda:now) as active:
        bybit._private_get=offline
        assert launcher.run_cycle(args,bybit,account_lease=active)==1
        assert len(sent)==1 and sent[0]['side']=='Sell'
    snapshot=json.loads((tmp_path/'.local/state/live-risk-snapshot.json').read_bytes())
    assert snapshot['configured_protections']['verified_account_ownership'] is True
    assert snapshot['account_ownership']['account_uid_verified_at_binding'] is True
    assert snapshot['entry_account_observation'] is None


def test_main_cannot_enter_cycle_with_second_key_for_same_active_uid(tmp_path,monkeypatch):
    from scripts import run_supabase_live_executor as launcher
    monkeypatch.chdir(tmp_path)
    policy_path=tmp_path/'policy.json';write_policy(policy_path)
    second=tmp_path/'second.sqlite'
    arguments=['executor','--account-ownership-guard','--entry-account-policy',str(policy_path),
        '--entry-runtime-approval',str(tmp_path/'approval.json'),'--entry-model-sha256','a'*64,
        '--ml-mode','gate','--exit-data-fallback','--submission-risk-guard','--spot-reservation-guard',
        '--local-order-reservations','--order-submission-journal',str(second),
        '--decision-outbox',str(tmp_path/'decisions.sqlite'),'--execution-controls',str(tmp_path/'controls.json'),
        '--drawdown-state',str(tmp_path/'peak.json'),'--max-portfolio-drawdown','.10',
        '--fractional-risk-policy',str(tmp_path/'fractional.json')]
    monkeypatch.setattr('sys.argv',arguments)
    monkeypatch.setattr(launcher.BybitPrivateClient,'from_env',lambda:client('fake-key-b'))
    monkeypatch.setattr(launcher,'run_cycle',lambda *a,**kw:pytest.fail('second executor entered cycle'))
    with account_execution_lease(tmp_path/'first.sqlite',client(),policy_path=policy_path,
            lock_directory=tmp_path/'.local/state/executor-ownership',clock=lambda:NOW):
        with pytest.raises(ValueError,match='another local executor'):launcher.main()
    assert not second.exists()
