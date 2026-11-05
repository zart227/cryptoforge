"""Versioned v2 native paper projections and causal fill-order archives.

Archive commits precede a single attached-DB cleanup/checkpoint transaction.
This component does not provide a prospective capture or economic admission.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import fcntl
import heapq
import hashlib
import json
import os
import platform
import sys
import decimal
from pathlib import Path
import re
import sqlite3
import threading

from cryptoforge.evidence_segments import _guard, _fingerprint, _sync_directory, canonical, digest, parse, require_sha
from cryptoforge.paper_capture_v3 import _metadata, _write_new, stamp, runtime_hashes as capture_hashes
from cryptoforge.paper_lifecycle import measure_resources
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_wallet_v2 import PaperWalletV2 as PaperWallet
from cryptoforge.paper_worker_v2 import PaperWorkerV2 as PaperWorker
from cryptoforge.paper_producer_v2 import load_kernel, runtime_hashes as kernel_runtime, VERSION, PRECISION
from cryptoforge.paper_worker_capture import _bounded as _bounded_json

SCHEMA = 'native-paper-producer-source-archive-v2'
SHARD_SCHEMA = {
    'identity': 'CREATE TABLE identity (pin TEXT NOT NULL,bucket INTEGER NOT NULL)',
    'head': 'CREATE TABLE head (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,sha TEXT NOT NULL,epoch INTEGER NOT NULL)',
    'records': '''CREATE TABLE records (seq INTEGER PRIMARY KEY,source TEXT NOT NULL,key TEXT NOT NULL,
        raw TEXT NOT NULL,previous TEXT NOT NULL,sha TEXT NOT NULL,UNIQUE(source,key))''',
}
CHECKPOINT_SCHEMA = {
    'identity': 'CREATE TABLE identity (pin TEXT NOT NULL)',
    'checkpoint': 'CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL,watermarks TEXT NOT NULL,epoch INTEGER NOT NULL)',
}
# source -> native database, table, columns, integer primary key
SOURCES = {
    'wallet.marks': ('main', 'marks', ('id','observed_at','payload'), True),
    'wallet.fill_order': ('main','fill_order',('sequence','intent_id'),True),
    'wallet.fills': ('main', 'fills', ('intent_id','payload'), False),
    'wallet.closed_segments': ('main', 'closed_segments', ('id','payload'), True),
    'wallet.intents': ('main', 'intents', ('id','pair','side','created_at','observed_at','status','reason'), False),
    'wallet.lots': ('main', 'lots', ('id','pair','opened_at','qty','cost','entry_fee_quote'), False),
    'wallet.day_anchors': ('main', 'state', ('key','value'), False),
    'worker.worker_events': ('worker', 'worker_events', ('id','observed_at','payload'), True),
    'worker.seen_predictions': ('worker', 'seen_predictions', ('id','status','observed_at'), False),
    'worker.intent_links': ('worker', 'intent_links', ('id','payload'), False),
}


# Mutable projection state is retained, never inserted into immutable history.
AUXILIARY = {
    'wallet.state': ('main','state',('key','value'),False),
    'wallet.filters': ('main','market_cache',('pair','filters'),False),
    'wallet.fill_counter': ('main','sqlite_sequence',('name','seq'),False),
    'worker.state': ('worker','worker_state',('key','value'),False),
}


@dataclass(frozen=True)
class NativeArchivePolicy:
    shards: int
    maximum_shard_bytes: int
    maximum_active_bytes: int
    maximum_active_rows: int
    maximum_records: int
    maximum_row_bytes: int
    maximum_batch_bytes: int
    maximum_total_bytes: int
    minimum_free_disk_bytes: int
    minimum_available_memory_bytes: int

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError('explicit positive native archive budgets required')
        if (not 1 <= self.shards <= 64 or self.shards & (self.shards-1)
                or not 65536 <= self.maximum_shard_bytes <= 64*1024*1024
                or not 65536 <= self.maximum_active_bytes <= 64*1024*1024
                or self.maximum_shard_bytes % 4096 or self.maximum_active_bytes % 4096
                or not 16 <= self.maximum_active_rows <= 4096
                or not 256 <= self.maximum_row_bytes <= 256*1024
                or not self.maximum_row_bytes <= self.maximum_batch_bytes <= 1024*1024
                or self.maximum_records > 2**63-1 or self.maximum_total_bytes > 2**63-1
                or self.maximum_total_bytes < 3*self.maximum_active_bytes+self.shards*65536
                or self.minimum_free_disk_bytes < self.maximum_total_bytes):
            raise ValueError('bounded shard/native/total archive policy required')


def _environment():
    return dict(python=sys.version,implementation=platform.python_implementation(),sqlite=sqlite3.sqlite_version,
        decimal=decimal.__version__,libmpdec=decimal.__libmpdec_version__,precision=PRECISION)


def _runtime():
    return {**capture_hashes(), **kernel_runtime(), 'native_archive_v2': digest(Path(__file__).read_bytes()),
        'worker_capture_json_guard':digest(Path(__file__).with_name('paper_worker_capture.py').read_bytes())}


def _market_maps(quotes,filters,policy):
    size=0
    for mapping in (quotes,filters):
        if type(mapping) is not dict or len(mapping)>policy.maximum_active_rows:
            raise ValueError('bounded native public market maps required')
        for pair,value in mapping.items():
            # Pair identities are values here: e.g. TOKEN/USDT is a legitimate
            # symbol, while credential-like keys inside a book still fail.
            size+=len(_bounded_json([pair,value],policy.maximum_row_bytes))
            if size>policy.maximum_batch_bytes:raise ValueError('bounded native public market batch required')


def _install_guards(wallet_path,worker_path,policy):
    """Enforce row caps inside the producer's own transaction, before commit.

    JSON payloads are already ASCII escaped by the kernel. Raw identifiers must
    be printable ASCII too. Their JSON encoding is bounded by twice the stored
    bytes plus fixed column/ID overhead; control/NUL and binary fields fail.
    """
    tables={}
    for alias,table,columns,_ in (*SOURCES.values(),*AUXILIARY.values()):
        if table!='sqlite_sequence':tables[alias,table]=columns
    for alias,path in (('main',wallet_path),('worker',worker_path)):
        db=sqlite3.connect(path)
        try:
            with db:
                for (owner,table),columns in tables.items():
                    if owner!=alias:continue
                    lengths='+'.join(f'coalesce(length(CAST(NEW.{c} AS BLOB)),0)' for c in columns)
                    bad_types=' OR '.join(f"typeof(NEW.{c}) NOT IN ('text','integer','null')" for c in columns)
                    bad_text=' OR '.join(f"(typeof(NEW.{c})='text' AND (length(CAST(NEW.{c} AS BLOB))!=length(NEW.{c}) OR instr(NEW.{c},char(0))>0 OR NEW.{c} GLOB ('*['||char(1)||'-'||char(31)||']*')))" for c in columns)
                    key=columns[0]
                    for operation in ('INSERT','UPDATE'):
                        growth=(f' OR ((SELECT count(*) FROM {table})>={policy.maximum_active_rows} AND NOT EXISTS(SELECT 1 FROM {table} WHERE {key}=NEW.{key}))'
                                if operation=='INSERT' else '')
                        db.execute(f'''CREATE TRIGGER guard_{table}_{operation.lower()} BEFORE {operation} ON {table}
                            WHEN 2*({lengths})+128>{policy.maximum_row_bytes} OR ({bad_types}) OR ({bad_text}){growth}
                            BEGIN SELECT RAISE(ABORT,'native v2 row representation/byte budget exceeded'); END''')
        finally:db.close()


def _schema(db, name='main'):
    rows=db.execute(f'SELECT type,name,tbl_name,sql FROM {name}.sqlite_master ORDER BY type,name').fetchmany(33)
    if len(rows)>32:raise ValueError('bounded original v2 native schema required')
    return rows


def _schema_pin(path):
    # V2 explicitly includes its transaction guards in the schema pin. The old
    # capture reader's blanket trigger ban is preserved for its original roots.
    db=_connect(path,writer=False,limit=64*1024*1024)
    try:return digest(canonical(_schema(db)))
    finally:db.close()


def _exact_schema(db, expected):
    rows = db.execute('SELECT name,type,sql FROM sqlite_master WHERE sql IS NOT NULL').fetchmany(4)
    norm = lambda s: ' '.join(s.split()).casefold()
    if (len(rows) != len(expected) or any(kind != 'table' for _,kind,_ in rows)
            or {n:norm(s) for n,_,s in rows} != {n:norm(s) for n,s in expected.items()}):
        raise ValueError('original archive SQLite schema required')


def _connect(path, *, writer, limit):
    _guard(path, limit=limit, allow_journal=writer)
    db = sqlite3.connect(path.as_uri()+('?mode=rw' if writer else '?mode=ro'), uri=True, timeout=1)
    try:
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA cache_size=-64')
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise ValueError('original DELETE-mode native archive required')
        if writer:
            db.execute('PRAGMA synchronous=FULL')
            pages = limit//db.execute('PRAGMA page_size').fetchone()[0]
            if db.execute(f'PRAGMA max_page_count={pages}').fetchone()[0] != pages:
                raise ValueError('native database already exceeds frozen page budget')
        else:
            db.execute('PRAGMA query_only=ON')
        return db
    except Exception:
        db.close();raise


def _key(source, identity):
    if source not in SOURCES:
        raise ValueError('known native source required')
    if SOURCES[source][3]:
        if type(identity) is not int or not 0 < identity < 2**63:
            raise ValueError('original positive native row ID required')
        return f'{identity:020d}'
    if type(identity) is not str or not 0 < len(identity.encode()) <= 1024:
        raise ValueError('bounded original native string key required')
    return identity


def _row(source, row, limit):
    spec = SOURCES[source]
    row = list(row)
    if len(row) != len(spec[2]) or any(type(x) not in (str,int,type(None)) for x in row):
        raise ValueError('original typed native row required')
    key = _key(source, row[0])
    raw = canonical(row)
    if len(raw) > limit:
        raise ValueError('native source row exceeds frozen byte limit')
    if source == 'wallet.fill_order':_key('wallet.fills',row[1])
    if source == 'wallet.intents' and row[5] not in {'filled','rejected'}:
        raise ValueError('pending native intents cannot be archived for deletion')
    if source == 'wallet.lots' and any(Decimal(row[i]) != 0 for i in (3,4,5)):
        raise ValueError('open native lots cannot be archived for deletion')
    if source == 'wallet.day_anchors':
        if not re.fullmatch(r'day_anchor:\d{4}-\d{2}-\d{2}', row[0]):
            raise ValueError('only immutable day-anchor state may be archived')
        datetime.fromisoformat(row[0].split(':',1)[1])
    return key, raw.decode()


def _chain(sequence, source, key, raw, previous):
    return digest(canonical(dict(sequence=sequence, source=source, key=key, raw=raw, previous=previous)))


class NativePaperArchiveV2:
    @classmethod
    def create(cls, root, *, source_protocol_sha256, kernel_root, expected_kernel_contract_sha256,
               expected_kernel_registration_sha256, policy, market, clock=None, exit_indicator=None):
        require_sha(source_protocol_sha256)
        if type(policy) is not NativeArchivePolicy:raise ValueError('typed v2 native archive policy required')
        root=Path(root).absolute();kernel_root=Path(kernel_root).absolute()
        if root.resolve()!=root or root==kernel_root or root.is_relative_to(kernel_root) or kernel_root.is_relative_to(root):
            raise ValueError('separate new nonsymlink native archive namespace required')
        kernel=load_kernel(kernel_root,expected_contract_sha256=expected_kernel_contract_sha256,
            expected_registration_sha256=expected_kernel_registration_sha256)
        clock=clock or (lambda:datetime.now(UTC))
        now=stamp(clock())
        if not stamp(kernel['registered_at'])<=now<stamp(kernel['start']):
            raise ValueError('native v2 archive must be registered before original kernel start')
        resources=measure_resources(root)
        if (resources['free_disk_bytes']<policy.minimum_free_disk_bytes
                or resources['available_memory_bytes'] is None
                or resources['available_memory_bytes']<policy.minimum_available_memory_bytes):
            raise ValueError('native archive preregistration resource floor failed')
        root.mkdir(mode=0o700,parents=True,exist_ok=False)
        config=PaperConfig(**kernel['config']);candidate_sha=kernel['candidate_sha256']
        worker_policy=kernel['worker_policy']
        wallet=PaperWallet(root/'wallet.sqlite',candidate_sha=candidate_sha,config=config,clock=clock)
        worker=PaperWorker(wallet,root/'worker.sqlite',policy=worker_policy,market=market,clock=clock,exit_indicator=exit_indicator)
        _install_guards(wallet.path,worker.path,policy)
        manifest=dict(schema_version=SCHEMA,root=str(root),source_protocol_sha256=source_protocol_sha256,
            candidate_sha256=candidate_sha,role=kernel['role'],config=kernel['config'],worker_policy=deepcopy(worker_policy),
            policy=asdict(policy),runtime=_runtime(),kernel_root=str(kernel_root),kernel_contract=kernel,
            kernel_contract_sha256=expected_kernel_contract_sha256,kernel_registration_sha256=expected_kernel_registration_sha256,
            source_schema=dict(immutable=SOURCES,auxiliary=AUXILIARY),
            wallet_schema_sha256=_schema_pin(wallet.path),worker_schema_sha256=_schema_pin(worker.path),
            environment=_environment(),registration_resources=resources,
            registered_at=now.isoformat(),research_only=True,live_eligible=False)
        pin=_write_new(root/'manifest.json',manifest)
        (root/'archive').mkdir(mode=0o700)
        (root/'archive.lock').touch(mode=0o600,exist_ok=False)
        for bucket in range(policy.shards):
            path=root/'archive'/f'{bucket:02d}.sqlite';db=sqlite3.connect(path)
            try:
                for sql in SHARD_SCHEMA.values():db.execute(sql)
                with db:
                    db.execute('INSERT INTO identity VALUES (?,?)',(pin,bucket))
                    db.execute('INSERT INTO head VALUES (1,0,?,0)',(digest(canonical([pin,bucket])),))
            finally:db.close()
            path.chmod(0o600)
        db=sqlite3.connect(root/'checkpoint.sqlite')
        try:
            for sql in CHECKPOINT_SCHEMA.values():db.execute(sql)
            with db:
                db.execute('INSERT INTO identity VALUES (?)',(pin,))
                db.execute('INSERT INTO checkpoint VALUES (1,0,?,0)',(canonical({}).decode(),))
        finally:db.close()
        (root/'checkpoint.sqlite').chmod(0o600)
        _sync_directory(root/'archive');_sync_directory(root);_sync_directory(root.parent)
        ready_at=stamp(clock())
        if not now<=ready_at<stamp(kernel['start']):
            raise ValueError('native archive setup missed original kernel start; no adoption')
        ready_pin=_write_new(root/'ready.json',dict(schema_version=SCHEMA,manifest_sha256=pin,registered_at=ready_at.isoformat()))
        if not ready_at<=stamp(clock())<stamp(kernel['start']):
            (root/'ready.json').unlink();_sync_directory(root)
            raise ValueError('native archive durable registration missed original kernel start; no adoption')
        return cls.resume(root,expected_manifest_sha256=pin,expected_ready_sha256=ready_pin,
            market=market,clock=clock,exit_indicator=exit_indicator)

    @classmethod
    def _load(cls, root, pin, ready_pin):
        root = Path(root).absolute()
        manifest = _metadata(root/'manifest.json',pin)
        if (manifest.get('schema_version') != SCHEMA or manifest.get('root') != str(root)
                or manifest.get('research_only') is not True or manifest.get('live_eligible') is not False
                or manifest.get('runtime') != _runtime()):
            raise ValueError('original native archive manifest/runtime required')
        ready=_metadata(root/'ready.json',ready_pin)
        kernel_root=Path(manifest['kernel_root'])
        kernel=load_kernel(kernel_root,expected_contract_sha256=manifest['kernel_contract_sha256'],
            expected_registration_sha256=manifest['kernel_registration_sha256'])
        if (root==kernel_root or root.is_relative_to(kernel_root) or kernel_root.is_relative_to(root)
                or manifest.get('kernel_contract')!=kernel or manifest.get('source_schema')!=parse(canonical(dict(immutable=SOURCES,auxiliary=AUXILIARY)))
                or any(manifest.get(k)!=kernel[k] for k in ('config','worker_policy','role','candidate_sha256'))
                or manifest.get('environment')!=_environment()
                or ready.get('schema_version')!=SCHEMA or ready.get('manifest_sha256')!=pin
                or not stamp(kernel['registered_at'])<=stamp(manifest['registered_at'])<=stamp(ready['registered_at'])<stamp(kernel['start'])):
            raise ValueError('original prospective v2 archive/kernel/environment required')
        obj = cls()
        obj.ready,obj.ready_sha256=ready,ready_pin
        obj.root,obj.manifest,obj.manifest_sha256 = root,manifest,pin
        obj.policy = NativeArchivePolicy(**manifest['policy'])
        resources=manifest['registration_resources']
        if (type(resources.get('available_memory_bytes')) is not int
                or resources['available_memory_bytes']<obj.policy.minimum_available_memory_bytes
                or type(resources.get('free_disk_bytes')) is not int
                or resources['free_disk_bytes']<obj.policy.minimum_free_disk_bytes):
            raise ValueError('original native archive preregistration resources required')
        obj._mutex,obj._local,obj._verified = threading.RLock(),threading.local(),{}
        obj._sealed,obj._sealed_stats = None,{}
        obj._highwater_cache=None
        return obj

    @classmethod
    def resume(cls, root, *, expected_manifest_sha256, expected_ready_sha256, market, clock=None, exit_indicator=None):
        obj = cls._load(root,expected_manifest_sha256,expected_ready_sha256)
        with obj._lease(writer=True):
            if (obj.root/'sealed.json').exists():
                raise ValueError('sealed source archive cannot resume native writers')
            obj._inventory(recovery=True)
            obj._recover_native()
            for bucket in range(obj.policy.shards):
                db=obj._shard(bucket,writer=True);db.close()
            obj._inventory()
            obj._check_native()
        obj._handles(market,clock or (lambda:datetime.now(UTC)),exit_indicator)
        return obj

    @classmethod
    def reader(cls, root, *, expected_manifest_sha256, expected_ready_sha256, expected_seal_sha256):
        obj = cls._load(root,expected_manifest_sha256,expected_ready_sha256)
        obj._seal_sha256=expected_seal_sha256
        obj._sealed = _metadata(obj.root/'sealed.json',expected_seal_sha256)
        if obj._sealed.get('manifest_sha256') != expected_manifest_sha256:
            raise ValueError('original native archive seal identity differs')
        with obj._lease(writer=False):obj._check_seal()
        return obj

    def _handles(self, market, clock, exit_indicator):
        self.wallet=object.__new__(ArchiveAwareWallet)
        self.wallet.path,self.wallet.candidate_sha = self.root/'wallet.sqlite',self.manifest['candidate_sha256']
        self.wallet.config,self.wallet.clock,self.wallet.archive = PaperConfig(**self.manifest['config']),clock,self
        self.wallet._runtime=kernel_runtime()
        self.wallet._identity=self.wallet._identity_value()
        self.worker=object.__new__(ArchiveAwareWorker)
        self.worker.wallet,self.worker.path = self.wallet,self.root/'worker.sqlite'
        self.worker.policy=deepcopy(self.manifest['worker_policy'])
        self.worker.market,self.worker.clock,self.worker.archive = market,clock,self
        self.worker.exit_indicator=exit_indicator or (lambda pair:(False,[]))
        self.worker._frozen_identity=self.worker._identity_value()

    @contextmanager
    def _lease(self, *, writer):
        with self._mutex:
            depth=getattr(self._local,'depth',0)
            if depth:
                if writer and not self._local.writer:raise ValueError('cannot upgrade a native archive read lease')
                self._local.depth+=1
                try:yield
                finally:self._local.depth-=1
                return
            path=self.root/'archive.lock';_guard(path,limit=0)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                fcntl.flock(fd,(fcntl.LOCK_EX if writer else fcntl.LOCK_SH)|fcntl.LOCK_NB)
                self._local.depth,self._local.writer=1,writer
                yield
            finally:
                self._local.depth=0;os.close(fd)

    def _path(self,bucket):return self.root/'archive'/f'{bucket:02d}.sqlite'

    def _inventory(self, recovery=False):
        if self.root.resolve()!=self.root or (self.root/'archive').resolve()!=self.root/'archive':
            raise ValueError('original native archive directory required')
        expected={'manifest.json','ready.json','archive.lock','wallet.sqlite','worker.sqlite','checkpoint.sqlite','archive'}
        if (self.root/'sealed.json').exists():expected.add('sealed.json')
        for path in self.root.iterdir():
            if path.name in expected:continue
            if recovery and (path.name in {n+'-journal' for n in ('wallet.sqlite','worker.sqlite','checkpoint.sqlite')}
                    or re.fullmatch(r'wallet\.sqlite-mj[0-9A-Za-z]+',path.name)):
                _guard(path,limit=self.policy.maximum_active_bytes*3+65536);continue
            raise ValueError('unregistered native archive file')
        if not expected <= {p.name for p in self.root.iterdir()}:raise ValueError('missing native archive file')
        names={f'{i:02d}.sqlite' for i in range(self.policy.shards)}
        for path in (self.root/'archive').iterdir():
            if path.name in names:continue
            if recovery and path.name.removesuffix('-journal') in names and path.name.endswith('-journal'):
                _guard(path,limit=self.policy.maximum_shard_bytes+65536);continue
            raise ValueError('unregistered archive shard')
        if not names <= {p.name for p in (self.root/'archive').iterdir()}:raise ValueError('missing archive shard')

    def _native(self, *, writer):
        db=_connect(self.root/'wallet.sqlite',writer=writer,limit=self.policy.maximum_active_bytes)
        try:
            for alias,name in (('worker','worker.sqlite'),('meta','checkpoint.sqlite')):
                _guard(self.root/name,limit=self.policy.maximum_active_bytes,allow_journal=writer)
                db.execute(f'ATTACH DATABASE ? AS {alias}',((self.root/name).as_uri()+('?mode=rw' if writer else '?mode=ro'),))
                if db.execute(f'PRAGMA {alias}.journal_mode').fetchone()[0]!='delete':raise ValueError('DELETE-mode native projections required')
                if writer:
                    db.execute(f'PRAGMA {alias}.synchronous=FULL')
                    pages=self.policy.maximum_active_bytes//db.execute(f'PRAGMA {alias}.page_size').fetchone()[0]
                    if db.execute(f'PRAGMA {alias}.max_page_count={pages}').fetchone()[0]!=pages:raise ValueError('native projection page budget exceeded')
            for name,key in (('main','wallet_schema_sha256'),('worker','worker_schema_sha256')):
                if digest(canonical(_schema(db,name)))!=self.manifest[key]:raise ValueError('original native projection schema required')
            expected={n:' '.join(s.split()).casefold() for n,s in CHECKPOINT_SCHEMA.items()}
            rows=db.execute('SELECT name,type,sql FROM meta.sqlite_master WHERE sql IS NOT NULL').fetchmany(3)
            if len(rows)!=2 or any(k!='table' for _,k,_ in rows) or {n:' '.join(s.split()).casefold() for n,_,s in rows}!=expected:
                raise ValueError('original native checkpoint schema required')
            if db.execute('SELECT pin FROM meta.identity').fetchmany(2)!=[(self.manifest_sha256,)]:raise ValueError('native checkpoint identity differs')
            return db
        except Exception:db.close();raise

    def _recover_native(self):
        sidecars=any(self.root.glob('*.sqlite-journal')) or any(self.root.glob('wallet.sqlite-mj*'))
        db=self._native(writer=True)
        try:
            if sidecars:
                # SQLite recovers hot journals. Make real writes to each verified
                # participant for non-hot leftovers; never unlink a journal.
                db.execute('BEGIN IMMEDIATE')
                for alias in ('main','worker'):
                    epoch=db.execute(f'PRAGMA {alias}.user_version').fetchone()[0]
                    if not 0<=epoch<2**31-2:raise ValueError('native recovery epoch exhausted')
                    db.execute(f'PRAGMA {alias}.user_version={epoch+1}')
                db.execute('UPDATE meta.checkpoint SET epoch=epoch+1 WHERE id=1');db.commit()
        finally:db.close()

    def _identity(self):
        current=self._load(self.root,self.manifest_sha256,self.ready_sha256)
        if current.manifest!=self.manifest or current.policy!=self.policy:raise ValueError('native archive in-memory identity differs')
        self._inventory()
        if self._sealed is not None or (self.root/'sealed.json').exists():raise ValueError('sealed native archive cannot be mutated')
        if (self.wallet.path!=self.root/'wallet.sqlite' or self.worker.path!=self.root/'worker.sqlite'
                or self.wallet.config!=PaperConfig(**self.manifest['config'])
                or self.wallet.candidate_sha!=self.manifest['candidate_sha256']
                or self.worker.policy!=self.manifest['worker_policy']):raise ValueError('native producer identity differs')

    def _native_identities(self):
        wallet=object.__new__(PaperWallet)
        wallet.path=self.root/'wallet.sqlite';wallet.candidate_sha=self.manifest['candidate_sha256']
        wallet.config=PaperConfig(**self.manifest['config']);wallet._runtime=kernel_runtime()
        wallet._identity=wallet._identity_value()
        worker=object.__new__(PaperWorker)
        worker.wallet=wallet;worker.path=self.root/'worker.sqlite';worker.policy=self.manifest['worker_policy']
        return wallet._identity,worker._identity_value()

    def _check_causal_projection(self,db):
        # Bounds are checked in SQLite before loading or decoding row payloads.
        for alias,table,columns,_ in (*SOURCES.values(),*AUXILIARY.values()):
            if db.execute(f'SELECT count(*) FROM {alias}.{table}').fetchone()[0]>self.policy.maximum_active_rows:
                raise ValueError('native active row budget exceeded')
            lengths='+'.join(f'coalesce(length(CAST({column} AS BLOB)),0)' for column in columns)
            if db.execute(f'SELECT 1 FROM {alias}.{table} WHERE ({lengths})>? LIMIT 1',(self.policy.maximum_row_bytes,)).fetchone():
                raise ValueError('bounded native projection row bytes required')
        high=db.execute('SELECT coalesce(max(sequence),0) FROM fill_order').fetchone()[0]
        counter=db.execute('SELECT name,seq FROM sqlite_sequence').fetchmany(2)
        if any(type(row[1]) is not int for row in counter) or counter!=([('fill_order',high)] if high else []):
            raise ValueError('native causal fill counter/high-water differs')
        if db.execute('SELECT 1 FROM fills f LEFT JOIN fill_order o ON o.intent_id=f.intent_id WHERE o.sequence IS NULL LIMIT 1').fetchone():
            raise ValueError('native causal fill order missing')
        if db.execute('SELECT 1 FROM fill_order o LEFT JOIN fills f ON f.intent_id=o.intent_id WHERE f.intent_id IS NULL OR o.sequence<=0 LIMIT 1').fetchone():
            raise ValueError('native causal fill order orphaned')
        fills={}
        for sequence,identity,raw in db.execute('SELECT o.sequence,o.intent_id,f.payload FROM fill_order o JOIN fills f ON f.intent_id=o.intent_id'):
            fill=parse(raw)
            if (type(fill.get('fill_sequence')) is not int or fill['fill_sequence']!=sequence
                    or fill.get('producer_version')!=VERSION or fill.get('intent_id')!=identity
                    or fill.get('candidate_sha256')!=self.manifest['candidate_sha256']
                    or fill.get('mode')!='paper' or fill.get('side') not in {'Buy','Sell'}):
                raise ValueError('native causal fill identity differs')
            intent=db.execute('SELECT pair,side,status FROM intents WHERE id=?',(identity,)).fetchone()
            if intent!=(fill['pair'],fill['side'],'filled'):raise ValueError('native retained fill/intent differs')
            fills[identity]=fill
        for identity,pair,qty,basis,fee in db.execute('SELECT id,pair,qty,cost,entry_fee_quote FROM lots'):
            for raw in (qty,basis,fee):
                value=Decimal(raw)
                if not value.is_finite() or value<0 or len(value.as_tuple().digits)>4096 or abs(value.as_tuple().exponent)>4096:
                    raise ValueError('native nonnegative bounded lot state required')
            if Decimal(qty)==0 and (Decimal(basis)!=0 or Decimal(fee)!=0):
                raise ValueError('native empty lot retains unallocated basis')
            if identity not in fills or fills[identity]['side']!='Buy' or fills[identity]['pair']!=pair:
                raise ValueError('native lot lost original causal entry fill')

    def _check_native(self):
        archived_highwaters=self._archive_highwaters()
        db=self._native(writer=False)
        try:
            wallet_identity,worker_identity=self._native_identities()
            if db.execute("SELECT value FROM state WHERE key='policy'").fetchone()!=(wallet_identity,):raise ValueError('native v2 wallet identity differs')
            if db.execute("SELECT value FROM worker.worker_state WHERE key='identity'").fetchone()!=(worker_identity,):raise ValueError('native v2 worker identity differs')
            watermarks=parse(db.execute('SELECT watermarks FROM meta.checkpoint WHERE id=1').fetchone()[0])
            if (type(watermarks) is not dict or any(k not in archived_highwaters or type(v) is not int or v<0 or v>=2**63
                                                  for k,v in watermarks.items())):raise ValueError('original native high-water checkpoint required')
            for source,(alias,table,columns,integer) in SOURCES.items():
                if db.execute(f'SELECT count(*) FROM {alias}.{table}').fetchone()[0]>self.policy.maximum_active_rows:
                    raise ValueError('native active row budget exceeded')
                if integer and db.execute(f'SELECT coalesce(max({columns[0]}),0) FROM {alias}.{table}').fetchone()[0]<max(watermarks.get(source,0),archived_highwaters[source]):
                    raise ValueError('native high-water anchor lost; IDs cannot reset')
            self._check_causal_projection(db)
        finally:db.close()

    def _stamp(self,path):
        stat=_guard(path,limit=self.policy.maximum_shard_bytes)
        return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns

    def _shard(self,bucket,writer=False):
        path=self._path(bucket)
        db=_connect(path,writer=writer,limit=self.policy.maximum_shard_bytes)
        try:
            _exact_schema(db,SHARD_SCHEMA)
            if db.execute('SELECT pin,bucket FROM identity').fetchmany(2)!=[(self.manifest_sha256,bucket)]:raise ValueError('archive shard identity differs')
            if writer and Path(str(path)+'-journal').exists():
                with db:db.execute('UPDATE head SET epoch=epoch+1 WHERE id=1')
            stat=self._stamp(path)
            if self._verified.get(bucket)!=stat:
                previous,seq=digest(canonical([self.manifest_sha256,bucket])),0
                for sequence,source,key,raw,before,sha in db.execute('SELECT seq,source,key,CASE WHEN length(CAST(raw AS BLOB))<=? THEN raw ELSE NULL END,previous,sha FROM records ORDER BY seq',(self.policy.maximum_row_bytes,)):
                    if raw is None:raise ValueError('bounded archive source row bytes required')
                    seq+=1
                    checked_key,checked_raw=_row(source,parse(raw),self.policy.maximum_row_bytes)
                    if (sequence!=seq or checked_key!=key or checked_raw!=raw or before!=previous
                            or sha!=_chain(seq,source,key,raw,previous) or self._bucket(source,key)!=bucket):
                        raise ValueError('archive original row/hash chain differs')
                    previous=sha
                if db.execute('SELECT seq,sha FROM head WHERE id=1').fetchone()!=(seq,previous):raise ValueError('archive shard counter/head differs')
                if stat!=self._stamp(path):raise ValueError('archive source changed while verifying')
                self._verified[bucket]=stat
            return db
        except Exception:db.close();raise

    def _bucket(self,source,key):return int(digest(canonical([source,key])),16)%self.policy.shards

    def _archive_highwaters(self):
        stamps=tuple(self._stamp(self._path(bucket)) for bucket in range(self.policy.shards))
        if self._highwater_cache is not None and self._highwater_cache[0]==stamps:return self._highwater_cache[1]
        result={source:0 for source in SOURCES if SOURCES[source][3]}
        for bucket in range(self.policy.shards):
            db=self._shard(bucket)
            try:
                for source in result:
                    row=db.execute('SELECT key FROM records WHERE source=? ORDER BY key DESC LIMIT 1',(source,)).fetchone()
                    if row:result[source]=max(result[source],int(row[0]))
            finally:db.close()
        self._highwater_cache=stamps,result
        return result

    def lookup(self,source,identity):
        key=_key(source,identity)
        with self._lease(writer=False):
            if self._sealed is not None:self._check_seal()
            db=self._shard(self._bucket(source,key))
            try:
                row=db.execute('SELECT raw FROM records WHERE source=? AND key=?',(source,key)).fetchone()
                return tuple(parse(row[0])) if row else None
            finally:db.close()

    def _budget(self,extra=0):
        self._inventory()
        total=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        reserve=3*self.policy.maximum_active_bytes+2*self.policy.maximum_batch_bytes+65536*self.policy.shards
        measured=measure_resources(self.root)
        if (total+reserve+extra>self.policy.maximum_total_bytes
                or measured['free_disk_bytes']<self.policy.minimum_free_disk_bytes+reserve
                or measured['available_memory_bytes'] is None
                or measured['available_memory_bytes']<self.policy.minimum_available_memory_bytes):
            raise ValueError('native archive resource/total budget exhausted')

    def _append_batch(self,batch):
        self._budget(sum(len(raw.encode()) for _,_,raw in batch)*3)
        total=0
        for bucket in range(self.policy.shards):
            db=self._shard(bucket)
            try:total+=db.execute('SELECT seq FROM head').fetchone()[0]
            finally:db.close()
        grouped={}
        for source,key,raw in batch:grouped.setdefault(self._bucket(source,key),[]).append((source,key,raw))
        for bucket,rows in grouped.items():
            db=self._shard(bucket,writer=True)
            try:
                with db:
                    seq,previous=db.execute('SELECT seq,sha FROM head').fetchone()
                    for source,key,raw in rows:
                        old=db.execute('SELECT raw FROM records WHERE source=? AND key=?',(source,key)).fetchone()
                        if old:
                            if old[0]!=raw:raise ValueError('immutable archived native row cannot change')
                            continue
                        if total>=self.policy.maximum_records:raise ValueError('global native archive record budget exhausted')
                        seq+=1;total+=1;sha=_chain(seq,source,key,raw,previous)
                        db.execute('INSERT INTO records VALUES (?,?,?,?,?,?)',(seq,source,key,raw,previous,sha));previous=sha
                    db.execute('UPDATE head SET seq=?,sha=? WHERE id=1',(seq,previous))
                self._verified[bucket]=self._stamp(self._path(bucket))
            finally:db.close()

    def _rows(self,db,source,archive_only=True):
        alias,table,columns,_=SOURCES[source]
        for row in db.execute(f'SELECT {",".join(columns)} FROM {alias}.{table} ORDER BY {columns[0]}'):
            if archive_only and source=='wallet.intents' and row[5]=='pending':continue
            if archive_only and source=='wallet.lots' and Decimal(row[3])>0:continue
            if source=='wallet.day_anchors' and not row[0].startswith('day_anchor:'):continue
            yield tuple(row)

    def _projection(self,db):
        keep={s:set() for s in SOURCES}
        for source in ('wallet.marks','wallet.closed_segments','worker.worker_events'):
            rows=list(self._rows(db,source))
            if rows:keep[source].add(rows[-1][0])
            if source=='wallet.marks':
                known=next((r for r in reversed(rows) if parse(r[2])['equity'] is not None),None)
                if known:keep[source].add(known[0])
        lots=db.execute('SELECT * FROM lots').fetchall()
        open_ids={r[0] for r in lots if Decimal(r[3])>0}
        pairs={r[1] for r in lots if Decimal(r[3])>0}
        latest={};order={}
        for sequence,identity,raw in db.execute('SELECT o.sequence,f.intent_id,f.payload FROM fill_order o JOIN fills f ON f.intent_id=o.intent_id ORDER BY o.sequence'):
            order[identity]=sequence;fill=parse(raw)
            if fill['side']=='Buy' and fill['pair'] in pairs:latest[fill['pair']]=fill
        keep['wallet.fills']=open_ids|{f['intent_id'] for f in latest.values()}
        if order:keep['wallet.fills'].add(max(order,key=order.get))
        keep['wallet.fill_order']={order[identity] for identity in keep['wallet.fills']}
        pending={r[0] for r in db.execute("SELECT id FROM intents WHERE status='pending'")}
        keep['wallet.intents']=pending|keep['wallet.fills']
        keep['worker.intent_links']=pending|keep['wallet.fills']
        anchors=[r[0] for r in self._rows(db,'wallet.day_anchors')]
        keep['wallet.day_anchors']=set(anchors[-2:])
        protected=dict(state=[r for r in db.execute('SELECT * FROM state ORDER BY key')
                             if not r[0].startswith('day_anchor:') or r[0] in keep['wallet.day_anchors']],
            lots=[list(r) for r in lots if Decimal(r[3])>0],
            fill_counter=db.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name').fetchall(),
            fill_order=[list(r) for r in db.execute('SELECT sequence,intent_id FROM fill_order ORDER BY sequence') if r[0] in keep['wallet.fill_order']],
            filters=db.execute('SELECT * FROM market_cache ORDER BY pair').fetchall(),
            worker=db.execute('SELECT * FROM worker.worker_state ORDER BY key').fetchall(),
            pending=db.execute("SELECT * FROM intents WHERE status='pending' ORDER BY id").fetchall())
        return keep,digest(canonical(protected))

    def _stage(self,name):
        """Crash-test boundary; no recovery action is inferred from a hook."""

    def compact(self):
        with self._lease(writer=True):
            self._identity();self._check_native();self._budget()
            before={n:_fingerprint(self.root/n,limit=self.policy.maximum_active_bytes) for n in ('wallet.sqlite','worker.sqlite','checkpoint.sqlite')}
            db=self._native(writer=False)
            signatures={}
            try:
                keep,protected=self._projection(db)
                batch=[];size=0
                for source in SOURCES:
                    hashed=hashlib.sha256()
                    for row in self._rows(db,source):
                        key,raw=_row(source,row,self.policy.maximum_row_bytes)
                        hashed.update(canonical([key,raw]))
                        if batch and (len(batch)>=256 or size+len(raw.encode())>self.policy.maximum_batch_bytes):
                            self._append_batch(batch);batch=[];size=0
                        batch.append((source,key,raw));size+=len(raw.encode())
                    signatures[source]=hashed.hexdigest()
                if batch:self._append_batch(batch)
            finally:db.close()
            self._stage('after_archive_commit')
            if before!={n:_fingerprint(self.root/n,limit=self.policy.maximum_active_bytes) for n in before}:
                raise ValueError('native source changed during archival; no cleanup')
            db=self._native(writer=True)
            try:
                db.execute('BEGIN IMMEDIATE')
                if self._projection(db)!=(keep,protected):raise ValueError('native protected projection changed')
                watermarks={}
                for source,(alias,table,columns,integer) in SOURCES.items():
                    hashed=hashlib.sha256();deletions=[]
                    for row in self._rows(db,source):
                        key,raw=_row(source,row,self.policy.maximum_row_bytes);hashed.update(canonical([key,raw]))
                        if self.lookup(source,row[0])!=row:raise ValueError('native row not durably archived; no cleanup')
                        if row[0] not in keep[source]:deletions.append(row[0])
                    if hashed.hexdigest()!=signatures[source]:raise ValueError('native archival input drift')
                    if integer:watermarks[source]=db.execute(f'SELECT coalesce(max({columns[0]}),0) FROM {alias}.{table}').fetchone()[0]
                    for key in deletions:db.execute(f'DELETE FROM {alias}.{table} WHERE {columns[0]}=?',(key,))
                if self._projection(db)[1]!=protected:raise ValueError('native cleanup changed cash/lot/day/pending state')
                db.execute('UPDATE meta.checkpoint SET generation=generation+1,watermarks=? WHERE id=1',(canonical(watermarks).decode(),))
                self._stage('before_projection_commit')
                db.commit()
            except Exception:db.rollback();raise
            finally:db.close()
            self._stage('after_projection_commit');self._check_native()
            return dict(status='native_projection_compacted',live_admission_granted=False)

    def _prepare(self):
        self._identity();self._check_native();self._budget()
        db=self._native(writer=False)
        try:
            pressure=any(db.execute(f'SELECT count(*) FROM {alias}.{table}').fetchone()[0]>=self.policy.maximum_active_rows-4
                         for alias,table,_,_ in SOURCES.values())
        finally:db.close()
        if pressure:self.compact()

    def _capacity(self,alias,table,growth,keep_free=0):
        for attempt in range(2):
            db=self._native(writer=False)
            try:count=db.execute(f'SELECT count(*) FROM {alias}.{table}').fetchone()[0]
            finally:db.close()
            if count+growth+keep_free<=self.policy.maximum_active_rows:return
            if not attempt:self.compact()
        raise ValueError('native active row reserve exhausted before producer write')

    def iter_rows(self,source):
        _key(source,1 if SOURCES[source][3] else 'key')
        with self._lease(writer=False):
            if self._sealed is not None:self._check_seal()
            connections=[]
            try:
                streams=[]
                for bucket in range(self.policy.shards):
                    db=self._shard(bucket);connections.append(db)
                    streams.append(((key,tuple(parse(raw))) for key,raw in db.execute('SELECT key,raw FROM records WHERE source=? ORDER BY key',(source,))))
                native=self._native(writer=False);connections.append(native)
                streams.append(((_key(source,row[0]),row) for row in self._rows(native,source,archive_only=False)))
                previous,value=None,None
                for key,row in heapq.merge(*streams,key=lambda item:item[0]):
                    if key==previous:
                        if row!=value:raise ValueError('active/archive duplicate source mismatch')
                        continue
                    previous,value=key,row;yield row
                if self._sealed is not None:self._check_seal()
            finally:
                for db in connections:db.close()

    def iter_auxiliary_rows(self,source):
        if source not in AUXILIARY:raise ValueError('known native v2 auxiliary source required')
        alias,table,columns,_=AUXILIARY[source]
        with self._lease(writer=False):
            if self._sealed is not None:self._check_seal()
            db=self._native(writer=False)
            try:
                self._check_causal_projection(db)
                for row in db.execute(f'SELECT {",".join(columns)} FROM {alias}.{table} ORDER BY {columns[0]}'):
                    if source=='wallet.state' and row[0].startswith('day_anchor:'):continue
                    if len(canonical(row))>self.policy.maximum_row_bytes:raise ValueError('bounded auxiliary source row required')
                    yield tuple(row)
                if self._sealed is not None:self._check_seal()
            finally:db.close()

    def seal(self):
        with self._lease(writer=True):
            self._identity();self.compact()
            files=['wallet.sqlite','worker.sqlite','checkpoint.sqlite','ready.json']+[f'archive/{i:02d}.sqlite' for i in range(self.policy.shards)]
            receipt=dict(schema_version=SCHEMA,manifest_sha256=self.manifest_sha256,
                files={n:_fingerprint(self.root/n,limit=max(self.policy.maximum_active_bytes,self.policy.maximum_shard_bytes))['sha256'] for n in files},
                paper_evidence_pass=False,live_admission_granted=False)
            pin=_write_new(self.root/'sealed.json',receipt)
            return {**receipt,'seal_sha256':pin}

    def _check_seal(self):
        self._inventory()
        current=self._load(self.root,self.manifest_sha256,self.ready_sha256)
        if (current.manifest!=self.manifest
                or _metadata(self.root/'manifest.json',self.manifest_sha256)!=self.manifest
                or self.manifest['runtime']!=_runtime()
                or _metadata(self.root/'ready.json',self.ready_sha256)!=self.ready
                or _metadata(self.root/'sealed.json',self._seal_sha256)!=self._sealed):
            raise ValueError('original native archive metadata changed')
        expected={'wallet.sqlite','worker.sqlite','checkpoint.sqlite','ready.json'}|{f'archive/{i:02d}.sqlite' for i in range(self.policy.shards)}
        if set(self._sealed.get('files',{}))!=expected:raise ValueError('original sealed source inventory differs')
        for name,pin in self._sealed['files'].items():
            path=self.root/name;limit=max(self.policy.maximum_active_bytes,self.policy.maximum_shard_bytes)
            stat=_guard(path,limit=limit)
            identity=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            if self._sealed_stats.get(name)!=identity:
                if _fingerprint(path,limit=limit)['sha256']!=pin:raise ValueError('original sealed native source SHA differs')
                self._sealed_stats[name]=identity

    def audit(self):
        if self._sealed is None:raise ValueError('external original native archive seal required')
        with self._lease(writer=False):self._check_seal();self._check_native()
        counts={source:sum(1 for _ in self.iter_rows(source)) for source in SOURCES}
        auxiliary={source:sum(1 for _ in self.iter_auxiliary_rows(source)) for source in AUXILIARY}
        return dict(native_source_integrity_pass=True,source_counts=counts,auxiliary_counts=auxiliary,
            full_worker_or_host_qualified=False,paper_evidence_pass=False,
            economic_profitability_established=False,live_admission_granted=False,
            scope='native_v2_archive_and_active_causal_projection_only_not_captured_replay_or_admission')


class ArchiveAwareWallet(PaperWallet):
    def _db(self):return _connect(self.path,writer=True,limit=self.archive.policy.maximum_active_bytes)

    def enqueue(self,intent_id,pair,side,*,created_at):
        with self.archive._lease(writer=True):
            self.archive._prepare()
            old=self.archive.lookup('wallet.intents',intent_id)
            if old:
                if tuple(old[1:4])!=(pair,side,created_at.isoformat()):raise ValueError('archived paper intent cannot change')
                return False
            reserve=min(self.config.max_positions+2,self.archive.policy.maximum_active_rows-2) if side=='Buy' else 0
            self.archive._capacity('main','intents',1,reserve)
            return super().enqueue(intent_id,pair,side,created_at=created_at)

    def execute(self,intent_id,quote,filters,*,entry_cutoff=None):
        with self.archive._lease(writer=True):
            self.archive._prepare()
            old=self.archive.lookup('wallet.intents',intent_id)
            if old:return dict(status=old[5],duplicate=True)
            _bounded_json([quote,filters],self.archive.policy.maximum_row_bytes)
            db=self._db()
            try:
                intent=db.execute('SELECT pair,side FROM intents WHERE id=?',(intent_id,)).fetchone()
                owned=sum(Decimal(r[0])>0 for r in db.execute('SELECT qty FROM lots WHERE pair=?',((intent or [''])[0],)))
            finally:db.close()
            self.archive._capacity('main','fills',1)
            self.archive._capacity('main','fill_order',1)
            if intent and intent[1]=='Buy':self.archive._capacity('main','lots',1,4)
            elif intent:self.archive._capacity('main','closed_segments',owned)
            self._cache_room({filters['pair']:filters})
            return super().execute(intent_id,quote,filters,entry_cutoff=entry_cutoff)

    def mark(self,quotes,filters_by_pair=None):
        with self.archive._lease(writer=True):
            _market_maps(quotes,filters_by_pair or {},self.archive.policy)
            self.archive._prepare();self.archive._capacity('main','marks',1)
            self._cache_room(filters_by_pair or {})
            return super().mark(quotes,filters_by_pair)

    def _cache_room(self,filters):
        db=self._db()
        try:known={r[0] for r in db.execute('SELECT pair FROM market_cache')}
        finally:db.close()
        self.archive._capacity('main','market_cache',len(set(filters)-known))

    def cancel_pending(self,*args,**kwargs):
        with self.archive._lease(writer=True):
            self.archive._prepare();return super().cancel_pending(*args,**kwargs)

    def snapshot(self):
        with self.archive._lease(writer=False):
            value=super().snapshot()
            return {**value,'history_scope':'bounded_active_projection_not_full_history'}

    def pending_intents(self):
        with self.archive._lease(writer=False):return super().pending_intents()


class ArchiveAwareWorker(PaperWorker):
    def _db(self):return _connect(self.path,writer=True,limit=self.archive.policy.maximum_active_bytes)

    def _enqueue(self,identity,pair,side,created,payload,source_key=None):
        with self.archive._lease(writer=True):
            self.archive._prepare()
            if (self.archive.lookup('worker.intent_links',identity)
                    or self.archive.lookup('wallet.intents',identity)
                    or (source_key and self.archive.lookup('worker.seen_predictions',source_key))):return False
            if len(canonical(payload))>self.archive.policy.maximum_row_bytes-2048:raise ValueError('bounded native link payload required')
            reserve=min(self.wallet.config.max_positions+2,self.archive.policy.maximum_active_rows-2) if side=='Buy' else 0
            self.archive._capacity('main','intents',1,reserve)
            self.archive._capacity('worker','intent_links',1)
            if source_key:self.archive._capacity('worker','seen_predictions',1)
            observed=self.clock()
            if (not pair.endswith('/USDT') or side not in {'Buy','Sell'} or created.tzinfo is None
                    or not 0<=(observed-created).total_seconds()<=5):raise ValueError('original bounded native enqueue required')
            db=self.wallet._db()
            try:
                db.execute('ATTACH DATABASE ? AS worker_meta',(str(self.path),))
                pages=self.archive.policy.maximum_active_bytes//db.execute('PRAGMA worker_meta.page_size').fetchone()[0]
                if db.execute(f'PRAGMA worker_meta.max_page_count={pages}').fetchone()[0]!=pages:raise ValueError('worker page budget exceeded')
                db.execute('PRAGMA worker_meta.synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM worker_meta.intent_links WHERE id=?',(identity,)).fetchone():db.rollback();return False
                db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,NULL)',(identity,pair,side,created.isoformat(),observed.isoformat(),'pending'))
                db.execute('INSERT INTO worker_meta.intent_links VALUES (?,?)',(identity,json.dumps(payload,sort_keys=True,default=str)))
                if source_key:db.execute('INSERT INTO worker_meta.seen_predictions VALUES (?,?,?)',(source_key,'queued',observed.isoformat()))
                db.commit();return True
            except Exception:db.rollback();raise
            finally:db.close()

    def _seen(self,identity,status):
        with self.archive._lease(writer=True):
            self.archive._prepare()
            if not self.archive.lookup('worker.seen_predictions',identity):
                self.archive._capacity('worker','seen_predictions',1)
                return super()._seen(identity,status)

    def _event(self,payload):
        with self.archive._lease(writer=True):
            self.archive._prepare()
            if len(canonical(payload))>self.archive.policy.maximum_row_bytes-2048:raise ValueError('bounded native event payload required')
            self.archive._capacity('worker','worker_events',1)
            return super()._event(payload)

    def tick(self,predictions,**kwargs):
        with self.archive._lease(writer=True):
            kernel=self.archive.manifest['kernel_contract']
            expected=dict(window_start=stamp(kernel['start']),window_end=stamp(kernel['end']),entry_cutoff=stamp(kernel['entry_cutoff']))
            if kwargs!=expected:raise ValueError('original v2 kernel window/cutoff required')
            self.archive._prepare()
            selected=[];size=0
            for count,prediction in enumerate(predictions):
                if count>=self.archive.policy.maximum_active_rows:raise ValueError('bounded native prediction batch required')
                size+=len(_bounded_json(prediction,self.archive.policy.maximum_row_bytes))
                if size>self.archive.policy.maximum_batch_bytes:raise ValueError('bounded native prediction batch bytes required')
                identity=digest((prediction['candidate_sha256']+'|'+prediction['opportunity']).encode())
                if not self.archive.lookup('worker.seen_predictions',identity):selected.append(prediction)
            return super().tick(selected,**expected)
