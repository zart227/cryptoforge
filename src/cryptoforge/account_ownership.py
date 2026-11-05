"""One cooperating local executor per verified UID/endpoint, across API keys."""
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

from cryptoforge.account_verification import load_account_policy, observe_account
from cryptoforge.execution_controls import OrderControlBlocked, unique_fields
from cryptoforge.execution_ownership import credential_scope, execution_lease, save_identity


CANONICAL_ACCOUNT_ENDPOINT = 'https://api.bybit.com'


def require_canonical_account_endpoint(client):
    # Preserve old namespace keys. Reject aliases instead of silently adopting a
    # fresh normalized namespace while an older binding may still exist.
    if type(client.base_url) is not str or client.base_url != CANONICAL_ACCOUNT_ENDPOINT:
        raise ValueError('UID ownership requires exact canonical mainnet endpoint; explicit endpoint recovery required')


def reject_alternative_uid_bindings(directory, expected, registry):
    """Do not bootstrap over a retained older endpoint/alias account registry."""
    for index,path in enumerate(directory.glob('*.owner.json')):
        if index>=1024:raise ValueError('account registry exceeds bounded ownership review scope')
        if path==registry:continue  # Its full record is validated by the caller.
        item=path.lstat()
        if not stat.S_ISREG(item.st_mode) or item.st_size>64*1024:
            raise ValueError('unknown account registry; explicit recovery required')
        with path.open('rb') as stream:raw=stream.read(64*1024+1)
        if len(raw)>64*1024:raise ValueError('account registry exceeds bounded record size')
        record=json.loads(raw,object_pairs_hook=unique_fields)
        if (not isinstance(record,dict) or record.get('schema_version')!='execution-account-ownership-v1'
                or not isinstance(record.get('uid_sha256'),str) or len(record['uid_sha256'])!=64
                or any(c not in '0123456789abcdef' for c in record['uid_sha256'])
                or not isinstance(record.get('endpoint'),str) or not record['endpoint']):
            raise ValueError('unknown account registry; explicit recovery required')
        if record['uid_sha256']==expected['uid_sha256']:
            raise ValueError('another endpoint registry owns this UID; explicit recovery required')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read_record(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_fields)


def inode(path):
    item = path.stat()
    return item.st_dev, item.st_ino


def account_lock_key(uid_sha256,endpoint):
    return digest(json.dumps(dict(uid_sha256=uid_sha256,endpoint=endpoint),sort_keys=True))


def account_owner_identity(scope,policy,*,journal_path,policy_path,policy_sha):
    return dict({key:value for key,value in scope.items() if key != 'account_uid_verified'},
        schema_version='execution-account-ownership-v1',account_uid_verified_at_binding=True,
        uid_sha256=digest(policy.expected_uid),parent_uid_sha256=digest(policy.expected_parent_uid),
        journal_path=str(journal_path),account_policy_path=str(policy_path),account_policy_sha256=policy_sha)


def validate_record(record, expected, *, journal_path, policy, now):
    if (not isinstance(record, dict) or set(record) != set(expected) | {
            'journal_device', 'journal_inode', 'verified_identity'}
            or any(type(record[key]) is not type(value) or record[key] != value
                for key, value in expected.items())
            or type(record['journal_device']) is not int or type(record['journal_inode']) is not int
            or (record['journal_device'], record['journal_inode']) != inode(journal_path)):
        raise ValueError('account owner/journal lineage differs; explicit recovery required')
    proof = record['verified_identity']
    if (not isinstance(proof, dict) or proof.get('schema_version') != 'bybit-spot-account-observation-v1'
            or proof.get('source') != 'GET /v5/user/query-api'
            or proof.get('credential_sha256') != expected['credential_sha256']
            or proof.get('uid_sha256') != expected['uid_sha256']
            or proof.get('parent_uid_sha256') != expected['parent_uid_sha256']
            or any(proof.get(key) is not True for key in ('account_uid_matches_policy',
                'personal_unified_subaccount', 'spot_trade_only', 'wallet_permissions_empty',
                'ip_whitelist_matches_policy'))):
        raise ValueError('verified account binding proof required')
    observed = datetime.fromisoformat(proof['observed_at'])
    server = datetime.fromisoformat(proof['server_time'])
    if (observed.tzinfo is None or server.tzinfo is None or observed > now
            or not 0 <= (observed-server).total_seconds() <= policy.maximum_response_age_seconds):
        raise ValueError('invalid original account binding clock')


class AccountExecutionLease:
    def __init__(self, *, record, journal_path, client, lock_path, lock, protected_paths, machine_id):
        self.record, self.journal_path, self.client = record, journal_path, client
        self.lock_path, self.lock, self.machine_id = lock_path, lock, machine_id
        self.protected = {path: path.read_bytes() for path in protected_paths}
        self.pid, self.active = os.getpid(), True

    def assert_held(self, *, client=None, journal_path=None):
        if not self.active or self.pid != os.getpid():
            raise OrderControlBlocked('verified account lease is not active in this process')
        try:
            require_canonical_account_endpoint(client or self.client)
            if journal_path is not None and Path(journal_path).resolve() != self.journal_path:
                raise ValueError('journal differs from account lease')
            scope = credential_scope(client or self.client, machine_id=self.machine_id)
            if any(scope[key] != self.record[key] for key in ('credential_sha256','endpoint','host_sha256')):
                raise ValueError('account credential scope changed')
            locked = os.fstat(self.lock.fileno())
            if (inode(self.lock_path) != (locked.st_dev, locked.st_ino)
                    or inode(self.journal_path) != (self.record['journal_device'],self.record['journal_inode'])
                    or any(path.read_bytes() != raw for path,raw in self.protected.items())):
                raise ValueError('account ownership files or journal changed')
        except Exception as exc:
            raise OrderControlBlocked('verified account lease lost or incompatible; no new submissions') from exc

    def diagnostic(self):
        return dict(schema_version='active-local-account-lease-v1',
            uid_sha256=self.record['uid_sha256'], endpoint=self.record['endpoint'],
            host_sha256=self.record['host_sha256'], journal_path=str(self.journal_path),
            account_uid_verified_at_binding=True, current_permissions_verified=False,
            scope='cooperating_processes_shared_local_lock_directory_not_multi_host')


@contextmanager
def account_execution_lease(journal_path, client, *, policy_path, lock_directory, machine_id=None, clock=None):
    require_canonical_account_endpoint(client)
    clock = clock or (lambda: datetime.now(UTC))
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware account ownership clock required')
    journal_path, policy_path = Path(journal_path).resolve(), Path(policy_path).resolve()
    policy, policy_sha = load_account_policy(policy_path)
    scope = credential_scope(client, machine_id=machine_id)
    expected = account_owner_identity(scope,policy,journal_path=journal_path,
        policy_path=policy_path,policy_sha=policy_sha)
    key = account_lock_key(expected['uid_sha256'],expected['endpoint'])
    directory = Path(lock_directory)/'accounts'; directory.mkdir(parents=True,exist_ok=True)
    lock_path = directory/(key+'.lock')
    registry = directory/(key+'.owner.json')
    binding = journal_path.with_name(journal_path.name+'.account-owner.json')
    credential_binding = journal_path.with_name(journal_path.name+'.owner.json')
    lease = None
    with lock_path.open('a') as lock:
        os.fchmod(lock.fileno(),0o600)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another local executor owns this account UID/endpoint') from exc
        try:
            reject_alternative_uid_bindings(directory,expected,registry)
            if registry.exists() or binding.exists():
                if not registry.is_file() or not binding.is_file() or not journal_path.is_file():
                    raise ValueError('incomplete account binding; explicit recovery required')
                record = read_record(registry)
                if record != read_record(binding):
                    raise ValueError('account owner records differ; explicit recovery required')
                validate_record(record,expected,journal_path=journal_path,policy=policy,now=now)
            else:
                if journal_path.exists() or credential_binding.exists():
                    raise ValueError('existing journal cannot acquire UID ownership automatically')
                try:
                    proof = observe_account(client,policy,clock=clock)
                except Exception:
                    raise ValueError('fresh account binding unavailable or unqualified; no submissions') from None
                record = None
            # UID lock first, then existing credential lock. Neither owner record
            # is replaced, and a legacy journal is never silently adopted.
            with execution_lease(journal_path,client,lock_directory=lock_directory,machine_id=machine_id):
                if record is None:
                    device,number = inode(journal_path)
                    record = dict(expected,journal_device=device,journal_inode=number,verified_identity=proof)
                    save_identity(registry,record)
                    save_identity(binding,record)
                lease = AccountExecutionLease(record=record,journal_path=journal_path,client=client,
                    lock_path=lock_path,lock=lock,protected_paths=(registry,binding,credential_binding),
                    machine_id=machine_id)
                lease.assert_held()
                yield lease
        finally:
            if lease is not None:
                lease.active = False
            fcntl.flock(lock,fcntl.LOCK_UN)


class AccountLeaseOrderClient:
    def __init__(self,client,lease):
        self.client,self.lease = client,lease

    def __getattr__(self,name):
        return getattr(self.client,name)

    def _submit(self,method,intent):
        if not isinstance(self.lease,AccountExecutionLease):
            raise OrderControlBlocked('verified account lease required')
        self.lease.assert_held(client=self.client)
        return getattr(self.client,method)(**intent)

    def create_spot_market_order(self,**intent):
        return self._submit('create_spot_market_order',intent)

    def create_spot_limit_order(self,**intent):
        return self._submit('create_spot_limit_order',intent)
