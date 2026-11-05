"""Local single-process lease and immutable credential/host journal binding."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def credential_scope(client, *, machine_id=None):
    """Key fingerprint is conservative identity, not a verified exchange UID."""
    machine_id = machine_id or Path('/etc/machine-id').read_text().strip()
    if not machine_id or not client.api_key or not client.base_url:
        raise ValueError('explicit credential, endpoint and host identity required')
    digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
    return dict(schema_version='execution-ownership-v1',
        credential_sha256=digest(client.api_key), endpoint=client.base_url.rstrip('/'),
        host_sha256=digest(machine_id), account_uid_verified=False)


def save_identity(binding, identity):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=binding.parent, delete=False) as stream:
            temporary = stream.name
            json.dump(identity, stream, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, binding)
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return identity


def credential_lock_key(scope):
    return hashlib.sha256(json.dumps({key:scope[key] for key in
        ('credential_sha256','endpoint')},sort_keys=True).encode()).hexdigest()


def bind_journal(path, scope):
    path = path.resolve()
    identity = dict(scope, journal_path=str(path))
    binding = path.with_name(path.name + '.owner.json')
    if binding.exists():
        if json.loads(binding.read_bytes()) != identity:
            raise ValueError('journal credential/host binding differs; explicit recovery required')
        if not path.exists():
            raise ValueError('bound journal is missing; explicit recovery required')
        return identity
    if path.exists():
        raise ValueError('unbound existing journal cannot be adopted automatically')
    path.parent.mkdir(parents=True, exist_ok=True)
    return save_identity(binding, identity)


@contextmanager
def execution_lease(journal_path, client, *, lock_directory, machine_id=None):
    scope = credential_scope(client, machine_id=machine_id)
    # Same credentials/endpoint share a lock even if a caller selects a new DB.
    key = credential_lock_key(scope)
    lock_directory.mkdir(parents=True, exist_ok=True)
    lock_path = lock_directory / (key + '.lock')
    with lock_path.open('a') as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another local executor owns these credentials') from exc
        registry = lock_directory / (key + '.owner.json')
        expected = dict(scope, journal_path=str(journal_path.resolve()))
        if registry.exists() and json.loads(registry.read_bytes()) != expected:
            raise ValueError('credential owner registry differs; cannot switch journal path or host')
        bind_journal(journal_path, scope)
        try:
            from cryptoforge.order_submission_journal import OrderSubmissionJournal
            OrderSubmissionJournal(journal_path)
            if not registry.exists():
                save_identity(registry, expected)
            yield scope
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
