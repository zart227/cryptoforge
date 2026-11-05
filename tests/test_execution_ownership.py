import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptoforge.execution_ownership import credential_scope, execution_lease


def client(key='test-credential'):
    return SimpleNamespace(api_key=key, base_url='https://api.bybit.com')


def lease(path, root, **kwargs):
    return execution_lease(path, kwargs.pop('client', client()), lock_directory=root/'locks',
        machine_id=kwargs.pop('machine_id', 'test-host'), **kwargs)


def test_binding_has_no_secret_and_same_owner_can_restart(tmp_path):
    path = tmp_path/'journal.sqlite'
    with lease(path, tmp_path): pass
    with lease(path, tmp_path): pass
    raw = (tmp_path/'journal.sqlite.owner.json').read_text()
    assert 'test-credential' not in raw and 'test-host' not in raw
    assert json.loads(raw)['account_uid_verified'] is False
    assert (tmp_path/'journal.sqlite.owner.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('change', ['credential', 'host', 'endpoint'])
def test_changed_identity_cannot_use_existing_journal(tmp_path, change):
    path = tmp_path/'journal.sqlite'
    with lease(path, tmp_path): pass
    altered = client('other-key' if change == 'credential' else 'test-credential')
    if change == 'endpoint': altered.base_url = 'https://api-testnet.bybit.com'
    with pytest.raises(ValueError, match='binding differs|registry differs'):
        with lease(path, tmp_path, client=altered, machine_id='other-host' if change == 'host' else 'test-host'):
            pytest.fail('ownership bypass')


def test_second_journal_does_not_bypass_active_credential_lock(tmp_path):
    with lease(tmp_path/'first.sqlite', tmp_path):
        with pytest.raises(ValueError, match='another local executor'):
            with lease(tmp_path/'second.sqlite', tmp_path): pass
    assert not (tmp_path/'second.sqlite.owner.json').exists()


def test_new_path_after_restart_cannot_bypass_prior_journal(tmp_path):
    with lease(tmp_path/'first.sqlite', tmp_path): pass
    with pytest.raises(ValueError, match='cannot switch journal'):
        with lease(tmp_path/'second.sqlite', tmp_path): pass
    assert not (tmp_path/'second.sqlite').exists()


def test_missing_bound_journal_and_unbound_existing_journal_need_recovery(tmp_path):
    path = tmp_path/'journal.sqlite'
    with lease(path, tmp_path): pass
    path.unlink()
    with pytest.raises(ValueError, match='journal is missing'):
        with lease(path, tmp_path): pass
    unknown = tmp_path/'old.sqlite'; unknown.write_bytes(b'old evidence')
    with pytest.raises(ValueError, match='cannot be adopted'):
        with lease(unknown, tmp_path, client=client('other-key')): pass
    assert unknown.read_bytes() == b'old evidence'


def hold_child(root, ready):
    with lease(Path(root)/'journal.sqlite', Path(root)):
        ready.set()
        import time
        time.sleep(10)


def test_real_process_death_releases_lease_without_resetting_journal(tmp_path):
    context = multiprocessing.get_context('spawn')
    ready = context.Event(); process = context.Process(target=hold_child, args=(str(tmp_path), ready))
    process.start()
    try:
        assert ready.wait(5)
        original = (tmp_path/'journal.sqlite').read_bytes()
        with pytest.raises(ValueError, match='another local executor'):
            with lease(tmp_path/'journal.sqlite', tmp_path): pass
        process.kill(); process.join(5)
        assert not process.is_alive()
        with lease(tmp_path/'journal.sqlite', tmp_path): pass
        assert (tmp_path/'journal.sqlite').read_bytes() == original
    finally:
        if process.is_alive(): process.kill()
        process.join(5)
