"""Bounded original reference history and source-bound price forecasts.

An isolated research namespace, never a writer to the primary database or model
registry. Immutable source versions keep their first observed time across reads.
Unfinished polls cannot be silently resumed. Whole-worker/economic gates stay shut.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, localcontext
import fcntl
import math
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from time import monotonic

from cryptoforge.local_source_provenance import canonical, digest, parse, read_file, sha, stamp, _new_root, _write_new, _sync
from cryptoforge.reference_sources import MANDATORY, INTERVAL_MS, PublicReferenceClient, normalize_observation, request_url, source_pairs

SCHEMA='reference-source-ledger-v1'
FLAGS=dict(source_poll_completeness_verified=False,historical_known_at_verified=False,
           full_worker_or_host_qualified=False,paper_evidence_pass=False,
           economic_profitability_established=False,live_admission_granted=False,
           counts_as_real_executed_buys=False)
SQL={
 'state': 'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,head TEXT NOT NULL,pending TEXT)',
 'events': 'CREATE TABLE events (seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload BLOB NOT NULL,previous TEXT NOT NULL,sha TEXT NOT NULL)',
 'versions': 'CREATE TABLE versions (source_id TEXT NOT NULL,version TEXT NOT NULL,pair TEXT NOT NULL,open_ms INTEGER NOT NULL,raw BLOB NOT NULL,known_at TEXT NOT NULL,event_seq INTEGER NOT NULL,PRIMARY KEY(source_id,version)) WITHOUT ROWID',
 'forecasts': 'CREATE TABLE forecasts (id TEXT PRIMARY KEY,payload BLOB NOT NULL,event_seq INTEGER NOT NULL) WITHOUT ROWID',
}
for table in ('events','versions','forecasts'):
    for operation in ('UPDATE','DELETE'):
        name=f'{table}_no_{operation.lower()}'
        SQL[name]=f"CREATE TRIGGER {name} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable original source'); END"


@dataclass(frozen=True)
class ReferencePolicy:
    maximum_events:int=100000
    maximum_versions:int=50000
    maximum_forecasts:int=50000
    maximum_database_bytes:int=1024*1024*1024
    maximum_event_bytes:int=256*1024
    minimum_free_disk_mb:int=2048

    def __post_init__(self):
        if (any(type(v) is not int or v<1 for v in asdict(self).values())
                or self.maximum_events>1000000 or self.maximum_versions>1000000 or self.maximum_forecasts>1000000
                or not 65536<=self.maximum_database_bytes<=4*1024**3 or self.maximum_database_bytes%4096
                or not 4096<=self.maximum_event_bytes<=256*1024 or self.minimum_free_disk_mb<2048):
            raise ValueError('explicit bounded reference source policy required')


def _runtime_paths():
    here=Path(__file__).parent;root=here.parents[1]
    names=('reference_sources.py','reference_source_ledger.py','local_source_provenance.py',
           'local_source_observer.py','backend.py','model_training.py','supabase_executor.py')
    paths={name:here/name for name in names}
    paths.update({name:root/'scripts'/name for name in ('capture_reference_sources.py','audit_local_source_provenance.py')})
    return paths


def runtime_hashes():
    current={name:digest(path.read_bytes()) for name,path in _runtime_paths().items()}
    if current!=_LOADED_RUNTIME:raise ValueError('reference runtime changed; new process/namespace required')
    return current


def _environment():
    return dict(python=list(sys.version_info[:3]),sqlite=sqlite3.sqlite_version,feature_decimal_precision=28)


def _artifact(raw):
    from cryptoforge.model_training import FEATURE_NAMES
    if type(raw) is not bytes or not 0<len(raw)<=65536:raise ValueError('bounded original model bytes required')
    a=parse(raw);config=a['config']
    expected=dict(timeframe='5m',input_candle_state='closed_only',feature_calculation_contract='bounded-window-candle-v1',feature_lookback_candles=120,horizon_candles=3)
    if (a.get('model_family')!='pure-python-logistic' or a.get('feature_names')!=list(FEATURE_NAMES)
            or config.get('target_version')!='fixed-future-return-v1' or any(config.get(k)!=v for k,v in expected.items())):
        raise ValueError('explicit frozen closed120 price model required')
    for key in ('weights','means','stds'):
        values=a[key]
        if type(values) is not list or len(values)!=7 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
            raise ValueError('finite model vector required')
    if min(a['stds'])<=0 or type(a['bias']) not in (int,float) or not math.isfinite(a['bias']):
        raise ValueError('finite model normalization required')
    return a


def evaluate(observation,*,started=None,recorded=None):
    try:
        derived=normalize_observation(observation)
        if started is not None and not stamp(started)<=stamp(observation['prepared_at'])<=stamp(observation['completed_at'])<=stamp(recorded):
            raise ValueError('source timestamps outside original observer call')
        return derived
    except (ValueError,TypeError,KeyError,OverflowError):
        return dict(pair=observation.get('pair'),status='invalid',reason='invalid_original_observation',rows=[],known_at=None,rate_limited=False)


def source_summary(derived):
    return {**{k:v for k,v in derived.items() if k!='rows'},'row_count':len(derived['rows']),
            'rows_sha256':digest(canonical(derived['rows']))}


def _file_identity(path):
    path=Path(path)
    s=path.lstat()
    if path.resolve()!=path or not path.is_file() or path.is_symlink() or s.st_nlink!=1:
        raise ValueError('original single-link source file required')
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)


def file_sha(path,maximum):
    before=_file_identity(path)
    if before[2]>maximum:raise ValueError('bounded source file required')
    import hashlib
    h=hashlib.sha256();total=0
    with path.open('rb') as f:
        while chunk:=f.read(65536):
            total+=len(chunk)
            if total>maximum:raise ValueError('source file grew beyond bound')
            h.update(chunk)
    if before!=_file_identity(path):raise ValueError('source file changed during hashing')
    return h.hexdigest()


def _guard_db(path,policy):
    if path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>policy.maximum_database_bytes:
        raise ValueError('original bounded reference database required')
    if any(Path(str(path)+s).exists() for s in ('-wal','-shm','-journal')):
        raise ValueError('unfinished reference SQLite transaction requires recovery')


def _database(path,policy,*,readonly):
    _guard_db(path,policy)
    db=sqlite3.connect(path.as_uri()+('?mode=ro' if readonly else '?mode=rw'),uri=True,timeout=1)
    if readonly:db.execute('PRAGMA query_only=ON')
    else:db.execute(f'PRAGMA max_page_count={policy.maximum_database_bytes//4096}')
    if db.execute('PRAGMA page_size').fetchone()[0]!=4096 or db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':
        db.close();raise ValueError('original reference storage format differs')
    definitions={name:sql for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if definitions!=SQL:
        db.close();raise ValueError('original reference database schema differs')
    for table,limit in [('events',policy.maximum_events),('versions',policy.maximum_versions),('forecasts',policy.maximum_forecasts)]:
        if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]>limit:
            db.close();raise ValueError('reference storage row budget exceeded')
    return db


def _insert_versions(db,rows,event_seq):
    for row in rows:
        db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?,?,?)',
                   (row['source_id'],row['version_sha256'],row['pair'],row['open_ms'],canonical(row['raw_row']),row['known_at'],event_seq))


def _sources_ready(windows,at):
    return all(w['derived']['status']=='ready'
        and 0<=(at-stamp(w['observation']['completed_at'])).total_seconds()<=600
        and 0<=at.timestamp()*1000-w['derived']['latest_close_ms']<=600000
        for w in windows.values())


def _event_time(kind,payload):
    field={'poll_prepared':'prepared_at','source_response':'recorded_at',
           'poll_complete':'completed_at','forecast':'recorded_at'}[kind]
    return stamp(payload[field])


def _rate_skip(pair,anchor,at):
    return dict(pair=pair,anchor_ms=anchor,url=request_url(pair,anchor),
        prepared_at=at.isoformat(),completed_at=at.isoformat(),elapsed_seconds=0,
        http_status=None,error_type='upstream_cooldown',raw_body_base64='',raw_body_sha256=digest(b''))


def _compute_forecast(artifact_raw,pair,windows,predicted_at):
    from cryptoforge.model_training import extract_features,predict_probability
    from cryptoforge.supabase_executor import CandleRow
    a=_artifact(artifact_raw)
    if pair not in a.get('pairs',[]):raise ValueError('forecast pair outside frozen model scope')
    rows=windows[pair]['derived']['rows'];known=stamp(windows[pair]['observation']['completed_at'])
    candles=[CandleRow(pair,pair.replace('/',''),datetime.fromtimestamp(r['open_ms']/1000,UTC),
        *[Decimal(v) for v in r['raw_row'][1:6]],cache_observed_at=known) for r in rows]
    with localcontext(Context(prec=28)):
        features=extract_features(candles,[row.volume for row in candles])
        probability=predict_probability(features,a['weights'],a['bias'],a['means'],a['stds'])
    bar=rows[-1]['open_ms'];target=datetime.fromtimestamp((bar+4*INTERVAL_MS)/1000,UTC)
    if not known<=predicted_at<target or not 0<=probability<=1 or any(not math.isfinite(v) for v in features):
        raise ValueError('future original forecast/input timing required')
    return dict(artifact_sha256=digest(artifact_raw),pair=pair,input_bar_open_ms=bar,
                input_contract='closed-bounded120-reference-source-v1',target_version='fixed-future-return-v1',
                predicted_at=predicted_at.isoformat(),target_information_end=target.isoformat(),
                features=list(features),long_probability=probability,
                sources=[dict(pair=p,event_sequence=w['event_seq'],response_sha256=digest(canonical(w['observation'])),
                              known_at=w['observation']['completed_at'],
                              row_count=len(w['derived']['rows']),
                              versions_sha256=digest(canonical([dict(source_id=r['source_id'],version_sha256=r['version_sha256']) for r in w['derived']['rows']])))
                         for p,w in sorted(windows.items())],
                scope='source_bound_price_forecast_not_cash_entry',**FLAGS)


class ReferenceLedger:
    @classmethod
    def create(cls,root,*,pairs=(),policy=None,artifact_raw=None,start=None,end=None,clock=None):
        policy=policy or ReferencePolicy();now=stamp((clock or (lambda:datetime.now(UTC)))())
        mode='prospective' if start is not None else 'diagnostic'
        start=stamp(start) if start is not None else now
        end=stamp(end) if end is not None else start+timedelta(days=31)
        if not start<end or (mode=='prospective' and not now<start):raise ValueError('new original prospective source window required')
        if artifact_raw is not None:
            a=_artifact(artifact_raw)
            information=[stamp(a['trained_at']),stamp(a['config']['fit_information_end']),stamp(a['config']['evaluation_information_end'])]
            if any(t>now for t in information) or information[1]>information[0]:raise ValueError('model information unavailable at original source freeze')
        root=Path(root).absolute()
        value=dict(schema_version=SCHEMA,root=str(root),mode=mode,registered_at=now.isoformat(),
                   start=start.isoformat(),end=end.isoformat(),pairs=source_pairs(pairs),mandatory_pairs=list(MANDATORY),
                   policy=asdict(policy),runtime=runtime_hashes(),environment=_environment(),
                   artifact_sha256=digest(artifact_raw) if artifact_raw is not None else None,**FLAGS)
        existing=root.parent
        while not existing.exists():existing=existing.parent
        if shutil.disk_usage(existing).free<policy.minimum_free_disk_mb*1024**2:raise ValueError('source disk reserve preserved')
        root=_new_root(root)
        if artifact_raw is not None:
            fd=os.open(root/'artifact.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(artifact_raw);f.flush();os.fsync(f.fileno())
        pin=_write_new(root/'manifest.json',value)
        path=root/'source.sqlite';db=sqlite3.connect(path)
        try:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
            for sql in SQL.values():db.execute(sql)
            with db:db.execute('INSERT INTO state VALUES (1,0,?,NULL)',(pin,))
        finally:db.close()
        path.chmod(0o600);(root/'writer.lock').touch(mode=0o600,exist_ok=False);_sync(root)
        completed=stamp((clock or (lambda:datetime.now(UTC)))())
        if completed<now or (mode=='prospective' and completed>=start):raise ValueError('source setup missed original start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=completed.isoformat()))
        final=stamp((clock or (lambda:datetime.now(UTC)))())
        if final<completed or (mode=='prospective' and final>=start):
            (root/'registered.json').unlink();_sync(root);raise ValueError('source completion missed original start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,
                             database_sha256=file_sha(path,policy.maximum_database_bytes),head_sha256=pin),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if type(reference) is not dict or set(reference)!= {'root','manifest_sha256','registration_sha256','database_sha256','head_sha256'}:
            raise ValueError('original external source ledger pins required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=65536);ready=read_file(root/'registered.json',maximum=65536)
        if digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256']):
            raise ValueError('original reference manifest/registration changed')
        value=parse(raw);registration=parse(ready);policy=ReferencePolicy(**value['policy'])
        expected={'manifest.json','registered.json','source.sqlite','writer.lock'}|({'artifact.json'} if value['artifact_sha256'] else set())
        if (root.resolve()!=root or {p.name for p in root.iterdir()}!=expected or value['root']!=str(root)
                or value['schema_version']!=SCHEMA or value['runtime']!=runtime_hashes() or value['environment']!=_environment()
                or value['mandatory_pairs']!=list(MANDATORY) or value['pairs']!=source_pairs([p for p in value['pairs'] if p not in MANDATORY])
                or registration['manifest_sha256']!=reference['manifest_sha256'] or any(value.get(k) is not False for k in FLAGS)
                or value['mode'] not in ('diagnostic','prospective')
                or not stamp(value['registered_at'])<=stamp(registration['registered_at'])
                or (value['mode']=='prospective' and not stamp(registration['registered_at'])<stamp(value['start']))):
            raise ValueError('original reference source namespace differs')
        if value['artifact_sha256']:
            artifact=read_file(root/'artifact.json',maximum=65536);_artifact(artifact)
            if digest(artifact)!=value['artifact_sha256']:raise ValueError('original frozen artifact differs')
        obj=cls();obj.root=root;obj.path=root/'source.sqlite';obj.manifest=value;obj.policy=policy
        obj.reference=dict(reference);obj.clock=clock or (lambda:datetime.now(UTC))
        with obj._lease():
            _guard_db(obj.path,policy)
            if file_sha(obj.path,policy.maximum_database_bytes)!=sha(reference['database_sha256']):
                raise ValueError('original external database pin differs')
            db=_database(obj.path,policy,readonly=True)
            try:
                state=db.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
                if state is None or state[1]!=sha(reference['head_sha256']):raise ValueError('original source head differs')
            finally:db.close()
        obj.identity=_file_identity(obj.path)
        return obj

    @contextmanager
    def _lease(self):
        lock=self.root/'writer.lock';read_file(lock,maximum=0)
        fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield
        finally:os.close(fd)

    def _check(self,*,active=True):
        if self.manifest['runtime']!=runtime_hashes() or self.identity!=_file_identity(self.path):
            raise ValueError('source runtime/database changed outside this writer')
        if digest(read_file(self.root/'manifest.json',maximum=65536))!=self.reference['manifest_sha256']:
            raise ValueError('original reference manifest changed')
        now=stamp(self.clock())
        if active and not stamp(self.manifest['start'])<=now<=stamp(self.manifest['end']):raise ValueError('original source window is not open')
        if shutil.disk_usage(self.root).free<self.policy.minimum_free_disk_mb*1024**2+3*self.policy.maximum_event_bytes:
            raise ValueError('source disk reserve preserved')
        return now

    def _append(self,kind,payload,*,pending,rows=(),forecast=None):
        now=self._check();raw=canonical(payload)
        if len(raw)>self.policy.maximum_event_bytes:raise ValueError('reference event byte budget exhausted')
        db=_database(self.path,self.policy,readonly=False)
        try:
            db.execute('BEGIN IMMEDIATE')
            seq,previous,_=db.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
            last=db.execute('SELECT kind,payload FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            prior_time=_event_time(last[0],parse(last[1])) if last else stamp(self.manifest['registered_at'])
            if not prior_time<=_event_time(kind,payload)<=now:raise ValueError('source event clock moved backwards')
            if seq>=self.policy.maximum_events:raise ValueError('source event budget exhausted')
            seq+=1;head=digest(canonical(dict(sequence=seq,kind=kind,payload=payload,previous_sha256=previous)))
            db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(seq,kind,raw,previous,head))
            _insert_versions(db,rows,seq)
            if forecast is not None:db.execute('INSERT INTO forecasts VALUES (?,?,?)',(forecast[0],canonical(forecast[1]),seq))
            if db.execute('SELECT count(*) FROM versions').fetchone()[0]>self.policy.maximum_versions:raise ValueError('source version budget exhausted')
            if db.execute('SELECT count(*) FROM forecasts').fetchone()[0]>self.policy.maximum_forecasts:raise ValueError('forecast budget exhausted')
            db.execute('UPDATE state SET seq=?,head=?,pending=? WHERE id=1',(seq,head,pending));db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
        self.identity=_file_identity(self.path)
        return seq

    def _windows(self,db):
        row=db.execute("SELECT payload FROM events WHERE kind='poll_complete' ORDER BY seq DESC LIMIT 1").fetchone()
        if row is None:return None,{}
        complete=parse(row[0]);windows={}
        for pair,sequence in complete['responses']:
            original=db.execute('SELECT payload FROM events WHERE seq=?',(sequence,)).fetchone()
            if original is None:raise ValueError('original source response missing')
            value=parse(original[0])
            derived=evaluate(value['observation'],started=value['request_started_at'],recorded=value['recorded_at'])
            if value['derived']!=source_summary(derived):raise ValueError('original source summary differs')
            windows[pair]={**value,'derived':derived,'event_seq':sequence}
        return complete,windows

    def _receipt(self):
        db=_database(self.path,self.policy,readonly=True)
        try:
            seq,head,pending=db.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
            complete,windows=self._windows(db)
            result=dict(reference=dict(self.reference,database_sha256=file_sha(self.path,self.policy.maximum_database_bytes),head_sha256=head),
                        events=seq,pending=pending,versions=db.execute('SELECT count(*) FROM versions').fetchone()[0],
                        forecasts=db.execute('SELECT count(*) FROM forecasts').fetchone()[0],
                        latest_status={p:w['derived']['status'] for p,w in windows.items()},**FLAGS)
            if complete:result['poll_completed_at']=complete['completed_at']
            return result
        finally:db.close()

    def receipt(self):
        with self._lease():self._check(active=False);return self._receipt()

    def poll(self,client=None):
        client=client or PublicReferenceClient()
        with self._lease():
            before=self._check();anchor=int(before.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
            db=_database(self.path,self.policy,readonly=True)
            try:
                if db.execute('SELECT pending FROM state WHERE id=1').fetchone()[0] is not None:raise ValueError('incomplete original source poll cannot resume')
                last,windows=self._windows(db)
            finally:db.close()
            if last and before<stamp(last['completed_at']):raise ValueError('source clock moved backwards')
            if last and (last['anchor_ms']==anchor or stamp(last['cooldown_until'])>before):
                return dict(**self._receipt(),reused_original_observation=True)
            poll_id=digest(canonical(dict(anchor_ms=anchor,prepared_at=before.isoformat(),head=self._receipt()['reference']['head_sha256'])))
            self._append('poll_prepared',dict(poll_id=poll_id,anchor_ms=anchor,prepared_at=before.isoformat(),pairs=self.manifest['pairs']),pending=poll_id)
            responses=[];cooldown=before;last_recorded=before;rate_blocked=False
            for pair in self.manifest['pairs']:
                started=stamp(self.clock());wall=monotonic()
                if started<last_recorded:raise ValueError('source clock moved backwards')
                try:observation=_rate_skip(pair,anchor,started) if rate_blocked else client.fetch(pair,anchor)
                except Exception as exc:
                    done=stamp(self.clock())
                    observation=dict(pair=pair,anchor_ms=anchor,url=request_url(pair,anchor),prepared_at=started.isoformat(),completed_at=done.isoformat(),
                                     elapsed_seconds=monotonic()-wall,http_status=None,error_type=type(exc).__name__,raw_body_base64='',raw_body_sha256=digest(b''))
                done=self._check()
                if done<started:raise ValueError('source request clock moved backwards')
                if (done-before).total_seconds()>75:raise ValueError('whole reference poll wall budget exhausted')
                derived=evaluate(observation,started=started,recorded=done)
                if observation.get('pair')!=pair or observation.get('anchor_ms')!=anchor:
                    raise ValueError('original requested source identity differs')
                if derived['known_at'] is not None and not before<=stamp(derived['known_at'])<=done:
                    raise ValueError('original reference completion time differs')
                seq=self._append('source_response',dict(poll_id=poll_id,observation=observation,derived=source_summary(derived),
                    request_performed=not rate_blocked,request_started_at=started.isoformat(),recorded_at=done.isoformat()),pending=poll_id,rows=derived['rows'])
                responses.append([pair,seq])
                last_recorded=done
                if derived['rate_limited']:
                    cooldown=max(cooldown,done+timedelta(minutes=10));rate_blocked=True
            complete=self._check()
            if complete<last_recorded:raise ValueError('source completion clock moved backwards')
            self._append('poll_complete',dict(poll_id=poll_id,anchor_ms=anchor,responses=responses,
                completed_at=complete.isoformat(),cooldown_until=cooldown.isoformat()),pending=None)
            return dict(**self._receipt(),reused_original_observation=False)

    def forecast(self,pair):
        with self._lease():
            now=self._check()
            if self.manifest['artifact_sha256'] is None:raise ValueError('forecast artifact was not frozen at creation')
            db=_database(self.path,self.policy,readonly=True)
            try:
                if db.execute('SELECT pending FROM state WHERE id=1').fetchone()[0] is not None:raise ValueError('incomplete original source poll')
                complete,windows=self._windows(db)
                if pair not in windows or set(windows)!=set(self.manifest['pairs']):raise ValueError('all mandatory reference sources required')
                if now<stamp(complete['completed_at']):raise ValueError('source clock moved backwards')
                if not _sources_ready(windows,now):
                    raise ValueError('missing/stale/failed mandatory reference source')
                identity=digest(canonical(dict(artifact=self.manifest['artifact_sha256'],pair=pair,bar=windows[pair]['derived']['rows'][-1]['open_ms'])))
                previous=db.execute('SELECT payload FROM forecasts WHERE id=?',(identity,)).fetchone()
                if previous:return dict(forecast_id=identity,stored=False,payload=parse(previous[0]),**FLAGS)
                raw=read_file(self.root/'artifact.json',maximum=65536)
                if digest(raw)!=self.manifest['artifact_sha256']:raise ValueError('original artifact changed')
                payload=_compute_forecast(raw,pair,windows,now)
            finally:db.close()
            recorded=self._check()
            if not now<=recorded<=now+timedelta(seconds=5):raise ValueError('forecast completion missed original clock')
            self._append('forecast',dict(forecast_id=identity,payload=payload,recorded_at=recorded.isoformat()),pending=None,forecast=(identity,payload))
            return dict(forecast_id=identity,stored=True,payload=payload,**FLAGS)


def audit_reference_ledger(reference,*,clock=None):
    ledger=ReferenceLedger.open(reference,clock=clock)
    with ledger._lease():
        ledger._check(active=False);db=_database(ledger.path,ledger.policy,readonly=True)
        scratch_path=None
        try:
            with tempfile.NamedTemporaryFile(prefix='reference-audit-',suffix='.sqlite',dir=ledger.root.parent,delete=False) as f:scratch_path=Path(f.name)
            scratch=sqlite3.connect(scratch_path);scratch.execute(f'PRAGMA max_page_count={ledger.policy.maximum_database_bytes//4096}')
            scratch.execute(SQL['versions']);scratch.execute(SQL['forecasts'])
            artifact_raw=read_file(ledger.root/'artifact.json',maximum=65536) if ledger.manifest['artifact_sha256'] else None
            if artifact_raw is not None and digest(artifact_raw)!=ledger.manifest['artifact_sha256']:raise ValueError('original artifact differs during audit')
            previous=reference['manifest_sha256'];count=0;pending=None;responses=[];windows={};last_windows={};last_poll=None;last_time=stamp(ledger.manifest['registered_at']);started=monotonic()
            for seq,kind,raw,prior,head in db.execute('SELECT seq,kind,payload,previous,sha FROM events ORDER BY seq'):
                if monotonic()-started>60:raise ValueError('source audit wall budget exhausted')
                payload=parse(raw)
                expected=digest(canonical(dict(sequence=seq,kind=kind,payload=payload,previous_sha256=previous)))
                if seq!=count+1 or prior!=previous or head!=expected or raw!=canonical(payload) or len(raw)>ledger.policy.maximum_event_bytes:
                    raise ValueError('original source event chain differs')
                if kind=='poll_prepared':
                    at=stamp(payload['prepared_at'])
                    poll_id=digest(canonical(dict(anchor_ms=payload['anchor_ms'],prepared_at=payload['prepared_at'],head=previous)))
                    if (pending is not None or payload['pairs']!=ledger.manifest['pairs'] or at<last_time
                            or payload['poll_id']!=poll_id or payload['anchor_ms']!=int(at.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
                            or (last_poll and (payload['anchor_ms']<=last_poll['anchor_ms'] or at<stamp(last_poll['cooldown_until'])))
                            or not stamp(ledger.manifest['start'])<=at<=stamp(ledger.manifest['end'])):
                        raise ValueError('original source poll ordering differs')
                    pending=payload;responses=[];windows={};expected_cooldown=at;last_response_time=at;rate_blocked=False
                elif kind=='source_response':
                    if pending is None or payload['poll_id']!=pending['poll_id']:raise ValueError('orphan source response')
                    observation=payload['observation'];derived=evaluate(observation,started=payload['request_started_at'],recorded=payload['recorded_at']);pair=observation['pair']
                    recorded=stamp(payload['recorded_at'])
                    if (source_summary(derived)!=payload['derived'] or len(responses)>=len(pending['pairs']) or pair!=pending['pairs'][len(responses)] or observation['anchor_ms']!=pending['anchor_ms']
                            or payload['request_performed'] is not (not rate_blocked)
                            or (rate_blocked and observation!=_rate_skip(pair,pending['anchor_ms'],stamp(payload['request_started_at'])))
                            or not stamp(pending['prepared_at'])<=recorded<=stamp(ledger.manifest['end'])
                            or not last_response_time<=stamp(payload['request_started_at'])<=recorded
                            or (derived['known_at'] is not None and not stamp(pending['prepared_at'])<=stamp(derived['known_at'])<=recorded)):
                        raise ValueError('original source availability/response differs')
                    if derived['rate_limited']:
                        expected_cooldown=max(expected_cooldown,recorded+timedelta(minutes=10));rate_blocked=True
                    responses.append([pair,seq]);windows[pair]={**payload,'derived':derived,'event_seq':seq};last_response_time=recorded
                    _insert_versions(scratch,derived['rows'],seq)
                elif kind=='poll_complete':
                    if (pending is None or payload['poll_id']!=pending['poll_id'] or payload['anchor_ms']!=pending['anchor_ms']
                            or payload['responses']!=responses or len(responses)!=len(ledger.manifest['pairs'])):
                        raise ValueError('missing mandatory source response')
                    done=stamp(payload['completed_at'])
                    if (not last_response_time<=done<=min(stamp(ledger.manifest['end']),stamp(pending['prepared_at'])+timedelta(seconds=75))
                            or stamp(payload['cooldown_until'])!=expected_cooldown):raise ValueError('original source poll time/cooldown differs')
                    for w in windows.values():
                        if w['derived']['known_at'] is not None and stamp(w['derived']['known_at'])>done:raise ValueError('source known_at after poll completion')
                    last_time=done;last_windows=windows;last_poll=payload;pending=None
                elif kind=='forecast':
                    if pending is not None or not last_windows or ledger.manifest['artifact_sha256'] is None:raise ValueError('unbound original forecast')
                    p=payload['payload'];at=stamp(p['predicted_at'])
                    recorded=stamp(payload['recorded_at'])
                    if (at<last_time or not at<=recorded<=min(stamp(ledger.manifest['end']),at+timedelta(seconds=5))
                            or not _sources_ready(last_windows,at)):
                        raise ValueError('unavailable reference source forecast')
                    recomputed=_compute_forecast(artifact_raw,p['pair'],last_windows,at)
                    identity=digest(canonical(dict(artifact=ledger.manifest['artifact_sha256'],pair=p['pair'],bar=p['input_bar_open_ms'])))
                    if recomputed!=p or identity!=payload['forecast_id']:raise ValueError('original source-to-forecast linkage differs')
                    scratch.execute('INSERT INTO forecasts VALUES (?,?,?)',(identity,canonical(p),seq));last_time=recorded
                else:raise ValueError('unknown original source event')
                previous=head;count+=1
            if pending is not None:raise ValueError('incomplete original source poll')
            if previous!=reference['head_sha256']:raise ValueError('original external source head differs')
            for table,order in [('versions','source_id,version'),('forecasts','id')]:
                actual=db.execute(f'SELECT * FROM {table} ORDER BY {order}')
                expected=scratch.execute(f'SELECT * FROM {table} ORDER BY {order}')
                while True:
                    a,b=actual.fetchmany(128),expected.fetchmany(128)
                    if a!=b:raise ValueError('original indexed first-seen/forecast projection differs')
                    if not a:break
            stored_state=db.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
            if stored_state!=(count,previous,None):raise ValueError('original mutable source head differs')
            ledger._check(active=False)
            if artifact_raw is not None and digest(read_file(ledger.root/'artifact.json',maximum=65536))!=digest(artifact_raw):raise ValueError('original artifact changed during audit')
            forecasts=db.execute('SELECT count(*) FROM forecasts').fetchone()[0]
            return dict(events_checked=count,versions_checked=db.execute('SELECT count(*) FROM versions').fetchone()[0],
                        forecasts_checked=forecasts,
                        latest_status={p:w['derived']['status'] for p,w in last_windows.items()},
                        source_trace_integrity_pass=True,original_source_forecast_linkage_pass=forecasts>0,
                        scope=ledger.manifest['mode'],**FLAGS)
        finally:
            db.close()
            if 'scratch' in locals():scratch.close()
            if scratch_path is not None:scratch_path.unlink(missing_ok=True)


_LOADED_RUNTIME={name:digest(path.read_bytes()) for name,path in _runtime_paths().items()}
