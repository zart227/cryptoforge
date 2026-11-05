"""Owned periodic market feeder with bounded operational (not study) retention."""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import fcntl
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

from cryptoforge.backend import resolve_backend
from cryptoforge.local_backend_route import observe_backend_route
from cryptoforge.local_source_provenance import canonical, digest, parse, read_file, stamp, sha, _new_root, _write_new, _sync
from cryptoforge.reference_aware_feeder import build_plan, run_cycle

FLAGS=dict(full_worker_or_host_qualified=False, paper_evidence_pass=False,
    economic_profitability_established=False, live_admission_granted=False)


@dataclass(frozen=True)
class FeederRetention:
    maximum_cycles:int=720
    maximum_bytes:int=384*1024**2
    maximum_cycle_bytes:int=96*1024**2
    maximum_success_age_seconds:int=86400
    minimum_free_disk_mb:int=2048

    def __post_init__(self):
        if (any(type(v) is not int for v in asdict(self).values()) or not 3<=self.maximum_cycles<=720
                or not 96*1024**2<=self.maximum_cycle_bytes<=128*1024**2
                or not 3*self.maximum_cycle_bytes<=self.maximum_bytes<=1024**3
                or not 3600<=self.maximum_success_age_seconds<=86400 or self.minimum_free_disk_mb<2048):
            raise ValueError('explicit bounded operational feeder retention required')


def runtime_hashes(repository):
    root=Path(repository)
    value=build_plan(root,root/'.local/state/live-universe.json')['runtime']
    for name, path in dict(managed_reference_feeder=Path(__file__),
            manage_cli=root/'scripts/manage_reference_feeder.py',
            route=root/'src/cryptoforge/local_backend_route.py',route_cli=root/'scripts/audit_local_backend_route.py',
            env_reader=root/'scripts/database_backend.py',compose=root/'docker/database.compose.yml',
            nginx=root/'docker/database-nginx.conf').items():
        value[name]=digest(path.read_bytes())
    return value


def _file_pin(path):
    h=__import__('hashlib').sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):h.update(block)
    return h.hexdigest()


def _inventory(root):
    result={}
    for folder,dirs,files in os.walk(root,followlinks=False):
        for name in dirs:
            p=Path(folder)/name
            if p.is_symlink():raise ValueError('operational cycle directory alias forbidden')
        for name in files:
            p=Path(folder)/name;relative=str(p.relative_to(root))
            if relative=='complete.json':continue
            info=p.lstat()
            if p.is_symlink() or not p.is_file() or info.st_nlink!=1 or info.st_size>32*1024**2:
                raise ValueError('bounded original operational cycle file required')
            if len(result)>=32:raise ValueError('operational cycle file count exhausted')
            result[relative]=dict(bytes=info.st_size,sha256=_file_pin(p))
    return result


class ManagedReferenceFeeder:
    @classmethod
    def create(cls,root,repository,env,*,policy=None,route=None,clock=None):
        repository=Path(repository).absolute();now=stamp((clock or (lambda:datetime.now(UTC)))())
        if repository.resolve()!=repository or resolve_backend(env).name!='local':
            raise ValueError('owned local repository/backend required')
        policy=policy or FeederRetention();runtime=runtime_hashes(repository)
        route=(route or (lambda:observe_backend_route(repository,env)))()
        if route['rest_instance_identity_verified'] is not True:
            raise ValueError('original local route observation required')
        root=_new_root(root);(root/'cycles').mkdir(mode=0o700);(root/'writer.lock').touch(mode=0o600)
        route_pin=_write_new(root/'initial-route.json',route)
        manifest=dict(schema_version='managed-reference-feeder-v1',root=str(root),repository=str(repository),
            uid=os.getuid(),python=sys.executable,python_version=list(sys.version_info[:3]),registered_at=now.isoformat(),
            runtime=runtime,policy=asdict(policy),initial_route_sha256=route_pin,
            sql_identity_sha256=route['row_binding']['sql_identity_sha256'],backend_url='http://127.0.0.1:54321',
            retention_scope='owned_terminal_success_operational_cycles_only_never_research_evidence',**FLAGS)
        pin=_write_new(root/'manifest.json',manifest)
        reg=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=stamp((clock or (lambda:datetime.now(UTC)))()).isoformat()))
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=reg),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256'}:
            raise ValueError('original managed feeder registration pins required')
        root=Path(reference['root']).absolute()
        raw=read_file(root/'manifest.json',maximum=65536);ready=read_file(root/'registered.json',maximum=4096)
        if digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256']):
            raise ValueError('original managed feeder registration differs')
        value=parse(raw);reg=parse(ready)
        if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root)
                or value['schema_version']!='managed-reference-feeder-v1' or value['uid']!=os.getuid()
                or value['python']!=sys.executable or value['python_version']!=list(sys.version_info[:3])
                or value['runtime']!=runtime_hashes(value['repository'])
                or any(value.get(k) is not False for k in FLAGS)
                or reg['manifest_sha256']!=reference['manifest_sha256']
                or not stamp(value['registered_at'])<=stamp(reg['registered_at'])
                or digest(read_file(root/'initial-route.json',maximum=32*1024**2))!=value['initial_route_sha256']):
            raise ValueError('owned managed feeder contract/runtime changed')
        obj=cls();obj.root=root;obj.manifest=value;obj.reference=dict(reference)
        obj.policy=FeederRetention(**value['policy']);obj.clock=clock or (lambda:datetime.now(UTC))
        obj._check();return obj

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0)
        fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _check(self):
        if {p.name for p in self.root.iterdir()}!={'manifest.json','registered.json','initial-route.json','writer.lock','cycles'}:
            raise ValueError('managed feeder inventory differs')
        if (self.root/'cycles').is_symlink():raise ValueError('original managed cycles directory required')
        if self.manifest['runtime']!=runtime_hashes(self.manifest['repository']):raise ValueError('managed feeder runtime changed')
        for name,key in (('manifest.json','manifest_sha256'),('registered.json','registration_sha256')):
            if digest(read_file(self.root/name,maximum=65536))!=self.reference[key]:raise ValueError('managed feeder static registration changed')
        now=stamp(self.clock())
        if now<stamp(self.manifest['registered_at']) or now<getattr(self,'last_clock',now):
            raise ValueError('managed feeder clock moved backwards')
        self.last_clock=now
        return now

    def _entries(self):
        rows=[]
        for path in (self.root/'cycles').iterdir():
            if path.is_symlink() or not path.is_dir() or not re.fullmatch('cycle-[0-9a-f]{32}',path.name):
                raise ValueError('original operational cycle namespace required')
            if not (path/'complete.json').exists():
                raise ValueError('incomplete operational cycle requires explicit investigation')
            completed=parse(read_file(path/'complete.json',maximum=65536))
            inventory=_inventory(path)
            if completed['files']!=inventory or type(completed['success']) is not bool:
                raise ValueError('original operational cycle receipt/files differ')
            size=sum(v['bytes'] for v in inventory.values())+(path/'complete.json').stat().st_size
            if size>self.policy.maximum_cycle_bytes:raise ValueError('operational cycle byte budget exhausted')
            if not stamp(completed['started_at'])<=stamp(completed['completed_at'])<=self._check():
                raise ValueError('operational cycle clock differs')
            rows.append(dict(path=path,completed=completed,bytes=size))
        return sorted(rows,key=lambda row:(row['completed']['completed_at'],row['path'].name))

    def _prepare(self):
        now=self._check();rows=self._entries();pruned=[]
        protected={r['path'] for r in [r for r in rows if r['completed']['success']][-2:]}
        total=sum(r['bytes'] for r in rows)
        for row in list(rows):
            old=now-stamp(row['completed']['completed_at'])>timedelta(seconds=self.policy.maximum_success_age_seconds)
            pressure=len(rows)+1>self.policy.maximum_cycles or total+self.policy.maximum_cycle_bytes>self.policy.maximum_bytes
            if not (old or pressure) or not row['completed']['success'] or row['path'] in protected:continue
            pruned.append(dict(cycle=row['path'].name,complete_sha256=_file_pin(row['path']/'complete.json'),bytes=row['bytes']))
            shutil.rmtree(row['path']);_sync(self.root/'cycles');rows.remove(row);total-=row['bytes']
        if len(rows)+1>self.policy.maximum_cycles or total+self.policy.maximum_cycle_bytes>self.policy.maximum_bytes:
            raise ValueError('protected operational retention budget exhausted')
        if shutil.disk_usage(self.root).free<self.policy.minimum_free_disk_mb*1024**2+self.policy.maximum_cycle_bytes:
            raise ValueError('managed feeder disk reserve preserved')
        return pruned

    def run(self,env,*,route=None,invoke=None):
        repository=Path(self.manifest['repository'])
        if resolve_backend(env).name!='local' or resolve_backend(env).url!=self.manifest['backend_url']:
            raise ValueError('original local backend required')
        route=route or (lambda:observe_backend_route(repository,env))
        invoke=invoke or run_cycle
        with self._lease():
            pruned=self._prepare()
            before=route()
            if before['row_binding']['sql_identity_sha256']!=self.manifest['sql_identity_sha256'] or before['rest_instance_identity_verified'] is not True:
                raise ValueError('registered local instance differs before refresh')
            started=self._check();folder=self.root/'cycles'/('cycle-'+uuid4().hex);folder.mkdir(mode=0o700)
            _write_new(folder/'started.json',dict(started_at=started.isoformat(),registration=self.reference,pruned_operational_cycles=pruned))
            _write_new(folder/'before.json',before)
            output=_new_root(folder/'run');plan=build_plan(repository,repository/'.local/state/live-universe.json')
            _write_new(output/'plan.json',plan)
            # An exception here intentionally leaves no complete marker. Unknown
            # mutation is never repeated automatically on the next timer tick.
            result=invoke(plan,output,env=env)
            _write_new(output/'result.json',result)
            success=result['success'] is True
            try:
                after=route();_write_new(folder/'after.json',after)
                success=success and after['rest_instance_identity_verified'] is True and after['row_binding']['sql_identity_sha256']==self.manifest['sql_identity_sha256'] and after['row_binding']['candle_freshness_pass'] is True
            except Exception as exc:
                _write_new(folder/'postcheck-error.json',dict(error_type=type(exc).__name__));success=False
            files=_inventory(folder);completed_at=self._check()
            complete=dict(started_at=started.isoformat(),completed_at=completed_at.isoformat(),success=success,
                reference_refresh_verified=result.get('reference_refresh_verified') is True,files=files,**FLAGS)
            pin=_write_new(folder/'complete.json',complete)
            if sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())>self.policy.maximum_cycle_bytes:
                raise ValueError('operational cycle exceeded registered byte cap')
            return dict(cycle_root=str(folder),complete_sha256=pin,success=success,
                reference_refresh_verified=complete['reference_refresh_verified'],pruned_success_cycles=len(pruned),**FLAGS)

    def status(self):
        with self._lease():
            self._check();rows=self._entries()
            return dict(reference=self.reference,completed_cycles=len(rows),bytes=sum(r['bytes'] for r in rows),
                latest=dict(root=str(rows[-1]['path']),**{k:v for k,v in rows[-1]['completed'].items() if k!='files'}) if rows else None,**FLAGS)
