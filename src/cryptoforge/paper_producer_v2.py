"""Identity and arithmetic context for a new paper-only producer namespace.

This kernel is deliberately incompatible with the frozen archive/capture v1
and its verifier. A future archive adapter must register this runtime explicitly.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, localcontext
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from cryptoforge.backend import resolve_backend


VERSION = 'paper-producer-v2-causal-fifo-exact-sizing'
PRECISION = 2048
CONTRACT_SCHEMA = 'paper-producer-kernel-contract-v2'
MAX_CONTRACT_BYTES = 65536


def runtime_hashes():
    names = ('paper_producer_v2.py', 'paper_wallet_v2.py', 'paper_worker_v2.py',
             'spot_buy_math_v2.py', 'spot_buy_math.py', 'paper_wallet.py',
             'exit_rules.py', 'live_learning_protocol.py', 'backend.py')
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in names}


@contextmanager
def arithmetic():
    # A fresh context prevents the caller's precision, traps or rounding from
    # changing a registered run. Affordability itself uses exact integer ratios.
    with localcontext(Context(prec=PRECISION)):
        yield


def pinned_operation(method):
    @wraps(method)
    def checked(self, *args, **kwargs):
        self._check_identity()
        with arithmetic():
            return method(self, *args, **kwargs)
    return checked


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _utc(value):
    if not isinstance(value,datetime) or value.tzinfo is None:
        raise ValueError('aware producer contract timestamp required')
    return value.astimezone(UTC)


def _sha(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('explicit producer candidate/study SHA required')


def register_kernel(root,*,candidate_sha,study_protocol_sha256,role,config,worker_policy,
                    backend_env,start,end,closeout_seconds,clock=None):
    """Freeze an opt-in kernel before start. Does not launch or qualify a study.

    Source capture, bounded archive, independent whole-worker replay and host
    admission remain mandatory downstream dependencies. No providers are called.
    """
    from cryptoforge.paper_wallet import PaperConfig
    _sha(candidate_sha);_sha(study_protocol_sha256)
    now=_utc((clock or (lambda:datetime.now(UTC)))());start=_utc(start);end=_utc(end)
    root=Path(root).absolute()
    if root.resolve()!=root or not now<start<end or type(closeout_seconds) is not int or not 0<closeout_seconds<(end-start).total_seconds():
        raise ValueError('new prospective producer window and closeout required')
    if type(config) is not PaperConfig or role not in {'candidate','control','stress'}:
        raise ValueError('explicit producer config and role required')
    from cryptoforge.spot_buy_math_v2 import _ratio
    for value in asdict(config).values():
        if isinstance(value,Decimal):_ratio(value,zero=True)
    # Canonical copy prevents caller mutation after registration. No credentials
    # or arbitrary extension fields are persisted from the worker policy.
    if type(worker_policy) is not dict or worker_policy.get('enabled') is not True or worker_policy.get('status')!='frozen':
        raise ValueError('enabled frozen producer worker policy required')
    runtime=worker_policy.get('runtime',{});exits=worker_policy.get('exits',{})
    maximum=runtime.get('maximum_new_signals_per_tick');wall=runtime.get('wall_budget_seconds')
    hold=exits.get('maximum_hold_seconds');shared=exits.get('shared_exit_signal')
    stop=Decimal(str(exits.get('stop_fraction')))
    if (type(maximum) is not int or not 1<=maximum<=4096 or type(wall) is not int or not 1<=wall<=3600
            or type(hold) is not int or not 1<=hold<=31536000 or type(shared) is not bool
            or not stop.is_finite() or not 0<stop<1):
        raise ValueError('bounded producer runtime and exits required')
    _ratio(stop)
    policy=dict(enabled=True,status='frozen',runtime=dict(maximum_new_signals_per_tick=maximum,wall_budget_seconds=wall),
                exits=dict(maximum_hold_seconds=hold,stop_fraction=str(stop),shared_exit_signal=shared))
    backend=resolve_backend(backend_env)
    if backend.name!='local':raise ValueError('explicit local backend required; no cloud fallback')
    value=dict(schema_version=CONTRACT_SCHEMA,producer_version=VERSION,root=str(root),registered_at=now.isoformat(),
        start=start.isoformat(),end=end.isoformat(),entry_cutoff=(end-timedelta(seconds=closeout_seconds)).isoformat(),
        closeout_seconds=closeout_seconds,candidate_sha256=candidate_sha,study_protocol_sha256=study_protocol_sha256,role=role,
        config=json.loads(json.dumps(asdict(config),default=str)),worker_policy=policy,
        source_backend=dict(name='local',api_origin=backend.url),runtime=runtime_hashes(),arithmetic_precision=PRECISION,
        scope='kernel_only_requires_new_archive_capture_replay_registration',
        full_worker_or_host_qualified=False,paper_evidence_pass=False,economic_profitability_established=False,live_admission_granted=False)
    raw=_canonical(value)
    if len(raw)>MAX_CONTRACT_BYTES:raise ValueError('bounded producer contract required')
    # Re-check actual UTC after validation, before the durable freeze.
    if not now<=_utc((clock or (lambda:datetime.now(UTC)))())<start:
        raise ValueError('producer registration missed original start')
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    fd=os.open(root/'kernel-contract.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        remaining=memoryview(raw)
        while remaining:
            count=os.write(fd,remaining)
            if count<=0:raise OSError('producer contract write did not advance')
            remaining=remaining[count:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    completed=_utc((clock or (lambda:datetime.now(UTC)))())
    if not now<=completed<start:
        raise ValueError('producer durable freeze missed original start; namespace cannot be adopted')
    # Completion is a separate durable pre-start observation. Without it a
    # partial/late freeze cannot be resumed as an original registration.
    complete=_canonical(dict(contract_sha256=hashlib.sha256(raw).hexdigest(),registered_at=completed.isoformat()))
    fd=os.open(root/'registered.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        remaining=memoryview(complete)
        while remaining:
            count=os.write(fd,remaining)
            if count<=0:raise OSError('producer registration write did not advance')
            remaining=remaining[count:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    final_clock=_utc((clock or (lambda:datetime.now(UTC)))())
    if not completed<=final_clock<start:
        (root/'registered.json').unlink()
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        raise ValueError('producer registration completion missed original start; namespace cannot be adopted')
    return dict(root=str(root),contract_sha256=hashlib.sha256(raw).hexdigest(),registration_sha256=hashlib.sha256(complete).hexdigest(),
                paper_evidence_pass=False,live_admission_granted=False)


def load_kernel(root,*,expected_contract_sha256,expected_registration_sha256):
    """Read only the separately pinned prospective kernel contract, offline."""
    _sha(expected_contract_sha256);_sha(expected_registration_sha256)
    root=Path(root).absolute()
    if root.resolve()!=root or {p.name for p in root.iterdir()}!={'kernel-contract.json','registered.json'}:
        raise ValueError('original separate producer contract namespace required')
    def read(name,pin):
        path=root/name;stat=path.lstat()
        if path.is_symlink() or not path.is_file() or stat.st_nlink!=1 or stat.st_size>MAX_CONTRACT_BYTES:
            raise ValueError('original bounded producer contract file required')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('original producer contract SHA differs')
        value=json.loads(raw)
        if raw!=_canonical(value):raise ValueError('canonical producer contract required')
        return value
    value=read('kernel-contract.json',expected_contract_sha256)
    registered=read('registered.json',expected_registration_sha256)
    if (value.get('schema_version')!=CONTRACT_SCHEMA or value.get('producer_version')!=VERSION
            or value.get('root')!=str(root) or value.get('runtime')!=runtime_hashes()
            or registered.get('contract_sha256')!=expected_contract_sha256
            or not _utc(datetime.fromisoformat(value['registered_at']))<=_utc(datetime.fromisoformat(registered['registered_at']))<_utc(datetime.fromisoformat(value['start']))):
        raise ValueError('original prospective producer contract/runtime required')
    _sha(value['candidate_sha256']);_sha(value['study_protocol_sha256'])
    start=_utc(datetime.fromisoformat(value['start']));end=_utc(datetime.fromisoformat(value['end']))
    cutoff=_utc(datetime.fromisoformat(value['entry_cutoff']))
    backend=value['source_backend'];parsed=urlsplit(backend.get('api_origin',''))
    if (value.get('role') not in {'candidate','control','stress'} or not start<cutoff<end
            or type(value.get('closeout_seconds')) is not int or end-cutoff!=timedelta(seconds=value['closeout_seconds'])
            or value.get('arithmetic_precision')!=PRECISION
            or value.get('scope')!='kernel_only_requires_new_archive_capture_replay_registration'
            or any(value.get(key) is not False for key in ('full_worker_or_host_qualified','paper_evidence_pass','economic_profitability_established','live_admission_granted'))
            or set(backend)!={'name','api_origin'} or backend['name']!='local' or parsed.scheme!='http'
            or parsed.hostname not in {'localhost','127.0.0.1','::1'} or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('original local kernel-only producer contract required')
    return value
