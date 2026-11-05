"""A supported account endpoint must not create a second ownership namespace."""
import json

import pytest

from cryptoforge.account_ownership import AccountLeaseOrderClient, account_execution_lease, account_lock_key, digest
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.execution_ownership import credential_lock_key, credential_scope
from test_account_migration import apply, prepare, setup_case
from test_account_ownership import NOW, client, lease
from test_account_verification import key_response, write_policy


CANONICAL = 'https://api.bybit.com'
UNSUPPORTED_ENDPOINTS = (
    'https://API.BYBIT.COM', 'HTTPS://api.bybit.com',
    'https://api.bybit.com:443', 'https://api.bybit.com/',
    'https://api.bybit.com//', 'https://api.bybit.com/v5',
    'https://api.bybit.com?mode=spot', 'https://api.bybit.com#spot',
    'https://user@api.bybit.com', 'https://user:password@api.bybit.com',
    'https://api.bytick.com', 'https://api-testnet.bybit.com',
    'https://api-demo.bybit.com', 'https://api.bybit.kz',
    'https://api.bybit.eu', 'https://custom.invalid',
    'http://api.bybit.com', 'https://api.bybit.com.',
    ' https://api.bybit.com', 'https://api.bybit.com\n', '', None, 1,
)


def tree(root, *, include_locks=True):
    """Include directory creation and every original file, not merely DB rows."""
    return {str(path.relative_to(root)): None if path.is_dir() else path.read_bytes()
        for path in root.rglob('*') if include_locks or path.suffix != '.lock'}


def canonical_client(key='fake-key-a'):
    bybit = client(key)
    bybit.base_url = CANONICAL
    return bybit


@pytest.mark.parametrize('endpoint', UNSUPPORTED_ENDPOINTS)
def test_unsupported_lease_endpoint_fails_before_policy_locks_journal_or_api(tmp_path, endpoint):
    bybit = canonical_client()
    bybit.base_url = endpoint
    # The absent policy ensures endpoint validation runs before policy IO, too.
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        with account_execution_lease(tmp_path / 'orders.sqlite', bybit,
                policy_path=tmp_path / 'absent-policy.json', lock_directory=tmp_path / 'locks',
                machine_id='fake-host', clock=lambda: NOW):
            pytest.fail('unsupported endpoint acquired an account lease')
    assert bybit.calls == [] and bybit.sent == []
    assert tree(tmp_path) == before


@pytest.mark.parametrize('endpoint', UNSUPPORTED_ENDPOINTS)
def test_unsupported_migration_endpoint_cannot_prepare_or_mutate_original_state(tmp_path, endpoint):
    case = setup_case(tmp_path)
    assert case.client.base_url == CANONICAL
    case.client.base_url = endpoint
    before = tree(tmp_path)
    with pytest.raises(ValueError):
        prepare(case)
    assert case.calls == []
    assert tree(tmp_path) == before


@pytest.mark.parametrize('endpoint', ['https://api.bytick.com', 'https://api.bybit.com:443',
    'https://api-testnet.bybit.com'])
def test_reviewed_apply_rechecks_endpoint_before_backup_or_owner_publication(tmp_path, endpoint):
    case = setup_case(tmp_path)
    result = prepare(case)
    before = tree(tmp_path)
    calls = list(case.calls)
    case.client.base_url = endpoint
    with pytest.raises(ValueError):
        apply(case, result)
    assert case.calls == calls
    assert tree(tmp_path) == before


@pytest.mark.parametrize('endpoint', ['https://api.bybit.com/', 'https://API.BYBIT.COM',
    'https://api.bybit.com:443', 'https://api.bytick.com', 'https://custom.invalid'])
def test_active_lease_endpoint_drift_blocks_buy_and_sell_before_raw_send(tmp_path, endpoint):
    bybit = canonical_client()
    with lease(tmp_path, bybit=bybit) as active:
        sender = AccountLeaseOrderClient(bybit, active)
        before = tree(tmp_path)
        bybit.base_url = endpoint
        for side in ('Buy', 'Sell'):
            with pytest.raises(OrderControlBlocked):
                sender.create_spot_market_order(symbol='BTCUSDT', side=side,
                    qty='1', order_link_id='endpoint-drift-' + side)
        assert bybit.sent == []
        assert tree(tmp_path) == before


def seed_legacy_alias_owner(root, endpoint):
    """Represent an intact pre-validation owner, without using the network."""
    bybit = canonical_client()
    with lease(root, bybit=bybit):
        pass
    original_scope = credential_scope(bybit, machine_id='fake-host')
    bybit.base_url = endpoint
    alias_scope = credential_scope(bybit, machine_id='fake-host')
    locks = root / 'locks'
    paths = [path for path in root.rglob('*.json')
        if path.name.endswith(('.owner.json', '.account-owner.json'))]
    for path in paths:
        record = json.loads(path.read_bytes())
        record['endpoint'] = endpoint
        path.write_text(json.dumps(record, sort_keys=True))
    (locks / (credential_lock_key(original_scope) + '.owner.json')).rename(
        locks / (credential_lock_key(alias_scope) + '.owner.json'))
    (locks / 'accounts' / (account_lock_key(digest('101'), CANONICAL) + '.owner.json')).rename(
        locks / 'accounts' / (account_lock_key(digest('101'), endpoint) + '.owner.json'))


@pytest.mark.parametrize('endpoint', ['https://api.bytick.com', 'https://API.BYBIT.COM',
    'https://api.bybit.com:443', 'https://api-testnet.bybit.com'])
def test_legacy_alias_owner_prevents_new_canonical_journal_and_is_preserved(tmp_path, endpoint):
    seed_legacy_alias_owner(tmp_path, endpoint)
    before = tree(tmp_path, include_locks=False)
    bybit = canonical_client('fake-key-b')
    with pytest.raises(ValueError):
        with lease(tmp_path, bybit=bybit, journal=tmp_path / 'new-orders.sqlite'):
            pytest.fail('legacy alias owner was bypassed with a new canonical journal')
    assert bybit.calls == [] and bybit.sent == []
    assert tree(tmp_path, include_locks=False) == before


@pytest.mark.parametrize('raw', [b'{', b'[]', b'null', b'1', b'{"uid_sha256": null}',
    b'{"uid_sha256": "unknown", "endpoint": "https://api.bytick.com"}',
    b'{"uid_sha256": "one", "uid_sha256": "two"}'])
def test_malformed_registry_blocks_bootstrap_without_adoption_or_replacement(tmp_path, raw):
    write_policy(tmp_path / 'policy.json')
    accounts = tmp_path / 'locks' / 'accounts'
    accounts.mkdir(parents=True)
    (accounts / ('a' * 64 + '.owner.json')).write_bytes(raw)
    bybit = canonical_client()
    before = tree(tmp_path, include_locks=False)
    with pytest.raises(ValueError):
        with lease(tmp_path, bybit=bybit):
            pytest.fail('malformed registry allowed a new owner')
    assert bybit.calls == [] and bybit.sent == []
    assert tree(tmp_path, include_locks=False) == before


def test_canonical_original_owner_restarts_without_namespace_or_query_change(tmp_path):
    bybit = canonical_client()
    with lease(tmp_path, bybit=bybit) as active:
        active.assert_held()
    before = tree(tmp_path)
    assert len(bybit.calls) == 1
    bybit._private_get = lambda *args: pytest.fail('matching owner restart queried the API')
    with lease(tmp_path, bybit=bybit) as active:
        active.assert_held()
        assert active.diagnostic()['endpoint'] == CANONICAL
    assert tree(tmp_path) == before


def test_distinct_verified_uids_share_lock_directory_concurrently_and_after_restart(tmp_path):
    first = canonical_client('fake-key-a')
    second = canonical_client('fake-key-b')
    second_policy = tmp_path / 'second-policy.json'
    write_policy(second_policy)
    policy = json.loads(second_policy.read_bytes())
    policy['expected_uid'] = '202'
    second_policy.write_text(json.dumps(policy))

    def query_second(path, params):
        second.calls.append((path, params))
        response = key_response(api_key=second.api_key, now=NOW)
        response['result']['userID'] = 202
        return response

    second._private_get = query_second
    second_journal = tmp_path / 'second-orders.sqlite'
    with lease(tmp_path, bybit=first) as first_active:
        with account_execution_lease(second_journal, second, policy_path=second_policy,
                lock_directory=tmp_path / 'locks', machine_id='fake-host',
                clock=lambda: NOW) as second_active:
            first_active.assert_held()
            second_active.assert_held()
            assert first_active.diagnostic()['uid_sha256'] == digest('101')
            assert second_active.diagnostic()['uid_sha256'] == digest('202')
    assert first.calls == second.calls == [('/v5/user/query-api', {})]
    before = tree(tmp_path)
    for bybit in (first, second):
        bybit._private_get = lambda *args: pytest.fail('matching UID restart queried the API')
    with lease(tmp_path, bybit=first) as active:
        active.assert_held()
    with account_execution_lease(second_journal, second, policy_path=second_policy,
            lock_directory=tmp_path / 'locks', machine_id='fake-host', clock=lambda: NOW) as active:
        active.assert_held()
    assert tree(tmp_path) == before
    assert first.sent == second.sent == []
