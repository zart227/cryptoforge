"""Reviewed credential-journal to UID binding migration; never submit or rewrite orders."""
from collections import Counter
from contextlib import contextmanager, ExitStack
from datetime import UTC, datetime
from decimal import Decimal
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge.account_ownership import (account_lock_key, account_owner_identity,
    inode, read_record, validate_record, require_canonical_account_endpoint, reject_alternative_uid_bindings)
from cryptoforge.account_verification import load_account_policy, observe_account
from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.execution_controls import unique_fields
from cryptoforge.execution_ownership import credential_scope, credential_lock_key
from cryptoforge.order_submission_journal import encoded


COLUMNS=('link','symbol','payload','sha','status','response','observed_at','last_error')
STATUSES={'prepared','unknown','acknowledged','observed','blocked','released_unfilled','released_closed'}
MAXIMUM_BYTES=64*1024*1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def clock_value(clock):
    now=clock()
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware migration clock required')
    return now.astimezone(UTC)


def json_bytes(value):
    return json.dumps(value,sort_keys=True,allow_nan=False).encode()


def implementation_hashes():
    names=('account_migration','account_ownership','account_verification','execution_ownership',
        'order_submission_journal','daily_risk_recovery')
    hashes={name:sha(Path(importlib.import_module('cryptoforge.'+name).__file__).read_bytes()) for name in names}
    hashes['migration_cli']=sha((Path(__file__).resolve().parents[2]/'scripts/migrate_journal_uid.py').read_bytes())
    return hashes


def bounded_read(path):
    path=Path(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size>MAXIMUM_BYTES:
        raise ValueError('bounded regular migration file required')
    with path.open('rb') as stream:raw=stream.read(MAXIMUM_BYTES+1)
    if len(raw)>MAXIMUM_BYTES:raise ValueError('migration file exceeds 64MiB scope')
    return raw


def output_path(path):
    path=Path(path).absolute()
    if path.is_symlink():raise ValueError('migration output must not be a symbolic link')
    return path.resolve()


def validate_output_paths(paths,*,backup_path,plan_path,lock_directory):
    reserved=[path for path in paths.values() if isinstance(path,Path)]
    reserved.extend(Path(str(paths['journal'])+suffix) for suffix in ('-wal','-shm','-journal'))
    reserved.append(Path(lock_directory).resolve())
    def overlaps(left,right):
        return left==right or left in right.parents or right in left.parents
    if overlaps(backup_path,plan_path) or any(overlaps(out,path)
            for out in (backup_path,plan_path) for path in reserved):
        raise ValueError('migration outputs overlap reserved inputs, ownership or lock paths')


def independent_backup(path,journal_path):
    item=path.lstat()
    if (not stat.S_ISREG(item.st_mode) or item.st_nlink!=1
            or (item.st_dev,item.st_ino)==inode(journal_path)):
        raise ValueError('independent regular backup required; links are not backups')


def reference(path):
    return dict(path=str(path),sha256=sha(bounded_read(path)))


def clean_journal(path):
    if any(os.path.lexists(str(path)+suffix) for suffix in ('-wal','-shm','-journal')):
        raise ValueError('quiescent DELETE-mode journal without SQLite sidecars required')


@contextmanager
def migration_scope(journal_path,client,*,policy_path,lock_directory,machine_id=None):
    require_canonical_account_endpoint(client)
    journal_path,policy_path=Path(journal_path).resolve(),Path(policy_path).resolve()
    lock_directory=Path(lock_directory).resolve()
    policy,policy_sha=load_account_policy(policy_path)
    scope=credential_scope(client,machine_id=machine_id)
    expected=account_owner_identity(scope,policy,journal_path=journal_path,
        policy_path=policy_path,policy_sha=policy_sha)
    credential_key=credential_lock_key(scope)
    account_key=account_lock_key(expected['uid_sha256'],expected['endpoint'])
    account_dir=lock_directory/'accounts';account_dir.mkdir(parents=True,exist_ok=True)
    paths=dict(journal=journal_path,policy=policy_path,
        credential_binding=journal_path.with_name(journal_path.name+'.owner.json'),
        credential_registry=lock_directory/(credential_key+'.owner.json'),
        account_binding=journal_path.with_name(journal_path.name+'.account-owner.json'),
        account_registry=account_dir/(account_key+'.owner.json'),
        intent=journal_path.with_name(journal_path.name+'.uid-migration-intent.json'))
    with ExitStack() as stack:
        for path in (account_dir/(account_key+'.lock'),lock_directory/(credential_key+'.lock')):
            lock=stack.enter_context(path.open('a'));os.fchmod(lock.fileno(),0o600)
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        reject_alternative_uid_bindings(account_dir,expected,paths['account_registry'])
        if not journal_path.is_file():raise ValueError('existing journal required; no initialization')
        owner=dict(scope,journal_path=str(journal_path))
        if any(json_bytes(read_record(paths[name]))!=json_bytes(owner)
                for name in ('credential_binding','credential_registry')):
            raise ValueError('matching existing credential binding and registry required')
        clean_journal(journal_path)
        paths['_journal_inode']=inode(journal_path)
        db=sqlite3.connect(journal_path.as_uri()+'?mode=ro',uri=True)
        try:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            yield paths,expected,policy,db
        finally:
            db.rollback();db.close()


def journal_audit(path,db,*,now,expected_inode):
    clean_journal(path)
    if inode(path)!=expected_inode:raise ValueError('journal inode changed during migration')
    if path.stat().st_size>MAXIMUM_BYTES:raise ValueError('migration journal exceeds 64MiB scope')
    if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':
        raise ValueError('only original DELETE journal mode supported')
    if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('journal integrity failure')
    objects=db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if objects!=[('table','order_submissions')]:raise ValueError('isolated submission schema required')
    columns=db.execute('PRAGMA table_info(order_submissions)').fetchall()
    required={'link','symbol','payload','sha','status','observed_at'}
    if (tuple(r[1] for r in columns)!=COLUMNS or any(r[2]!='TEXT' or bool(r[3])!=(r[1] in required)
            or r[5]!=(1 if r[1]=='link' else 0) for r in columns)):
        raise ValueError('original submission column contract required')
    count=0;statuses=Counter();logical=hashlib.sha256()
    for row in db.execute('SELECT '+','.join(COLUMNS)+' FROM order_submissions ORDER BY link'):
        link,symbol,raw,digest,status,response,observed,error=row
        payload=json.loads(raw,object_pairs_hook=unique_fields)
        if (not isinstance(payload,dict) or set(payload)!={'symbol','side','qty','order_link_id'}
                or payload['symbol']!=symbol or payload['order_link_id']!=link
                or not isinstance(symbol,str) or not symbol or not isinstance(link,str) or not link
                or payload['side'] not in {'Buy','Sell'} or type(payload['qty']) is not str
                or encoded(payload)!=raw or sha(raw.encode())!=digest or status not in STATUSES):
            raise ValueError('invalid original order intent or status')
        qty=Decimal(payload['qty']);stamp=datetime.fromisoformat(observed)
        if not qty.is_finite() or qty<=0 or stamp.tzinfo is None or stamp>now:
            raise ValueError('invalid original order amount or clock')
        if response is not None:
            parsed=json.loads(response,object_pairs_hook=unique_fields)
            json.dumps(parsed,allow_nan=False)
        if error is not None and type(error) is not str:raise ValueError('invalid original error field')
        logical.update(json_bytes(row)+b'\n');count+=1;statuses[status]+=1
    device,number=inode(path)
    ref=reference(path)
    if inode(path)!=expected_inode:raise ValueError('journal inode changed during audit')
    return dict(**ref,device=device,inode=number,row_count=count,
        status_counts=dict(sorted(statuses.items())),logical_rows_sha256=logical.hexdigest())


def snapshot(paths,db,*,now):
    return dict(journal=journal_audit(paths['journal'],db,now=now,expected_inode=paths['_journal_inode']),
        **{name:reference(paths[name]) for name in ('policy','credential_binding','credential_registry')})


def fresh_identity(client,policy,clock):
    try:return observe_account(client,policy,clock=clock)
    except Exception:raise ValueError('fresh UID/key verification unavailable; migration blocked') from None


def prepare_migration(*,journal_path,client,policy_path,lock_directory,backup_path,plan_path,
                      review_reference,machine_id=None,clock=None):
    clock=clock or (lambda:datetime.now(UTC))
    if not isinstance(review_reference,str) or not review_reference.strip():
        raise ValueError('explicit review reference required')
    backup_path,plan_path=output_path(backup_path),output_path(plan_path)
    with migration_scope(journal_path,client,policy_path=policy_path,lock_directory=lock_directory,
            machine_id=machine_id) as (paths,expected,policy,db):
        validate_output_paths(paths,backup_path=backup_path,plan_path=plan_path,lock_directory=lock_directory)
        if any(os.path.lexists(paths[name]) for name in ('account_binding','account_registry','intent')):
            raise ValueError('new review cannot replace an existing account binding or migration')
        if os.path.lexists(backup_path) or os.path.lexists(plan_path) or backup_path==plan_path:
            raise ValueError('new distinct backup/plan paths required')
        original=snapshot(paths,db,now=clock_value(clock))
        proof=fresh_identity(client,policy,clock)
        if snapshot(paths,db,now=clock_value(clock))!=original:raise ValueError('source changed during review')
        plan=dict(schema_version='reviewed-uid-journal-migration-v1',prepared_at=clock_value(clock).isoformat(),
            review_reference=review_reference,inputs=original,expected_account=expected,
            backup_path=str(backup_path),lock_directory=str(Path(lock_directory).resolve()),
            verified_identity_at_prepare=proof,implementation_sha256=implementation_hashes(),
            live_admission_granted=False,orders_submitted=False)
        raw=json_bytes(plan);publish_new(plan_path,raw)
    return dict(status='prepared_for_review',plan_sha256=sha(raw),row_count=original['journal']['row_count'],
        status_counts=original['journal']['status_counts'],live_admission_granted=False)


def publish_matching(path,raw):
    if os.path.lexists(path):
        if path.is_symlink() or bounded_read(path)!=raw:
            raise ValueError('existing migration output differs; never overwrite')
    else:
        publish_new(path,raw)


def apply_migration(*,plan_path,reviewed_plan_sha256,client,machine_id=None,clock=None):
    clock=clock or (lambda:datetime.now(UTC))
    plan_path=output_path(plan_path)
    raw=bounded_read(plan_path)
    if sha(raw)!=reviewed_plan_sha256:raise ValueError('independently reviewed plan SHA256 mismatch')
    plan=json.loads(raw,object_pairs_hook=unique_fields)
    keys={'schema_version','prepared_at','review_reference','inputs','expected_account',
        'backup_path','lock_directory','verified_identity_at_prepare','implementation_sha256',
        'live_admission_granted','orders_submitted'}
    if (not isinstance(plan,dict) or set(plan)!=keys
            or plan['schema_version']!='reviewed-uid-journal-migration-v1'
            or plan['live_admission_granted'] is not False or plan['orders_submitted'] is not False
            or plan['implementation_sha256']!=implementation_hashes()
            or not isinstance(plan['review_reference'],str) or not plan['review_reference'].strip()):
        raise ValueError('unsupported or changed migration implementation/review')
    prepared=datetime.fromisoformat(plan['prepared_at'])
    if prepared.tzinfo is None or prepared>clock_value(clock):raise ValueError('invalid migration review clock')
    inputs=plan['inputs']
    with migration_scope(inputs['journal']['path'],client,policy_path=inputs['policy']['path'],
            lock_directory=plan['lock_directory'],machine_id=machine_id) as (paths,expected,policy,db):
        backup_path=output_path(plan['backup_path'])
        validate_output_paths(paths,backup_path=backup_path,plan_path=plan_path,lock_directory=plan['lock_directory'])
        if (json_bytes(expected)!=json_bytes(plan['expected_account'])
                or json_bytes(snapshot(paths,db,now=clock_value(clock)))!=json_bytes(inputs)):
            raise ValueError('journal or owner inputs changed after review')
        fresh=fresh_identity(client,policy,clock)
        if snapshot(paths,db,now=clock_value(clock))!=inputs:raise ValueError('source changed during verification')
        if os.path.lexists(backup_path):independent_backup(backup_path,paths['journal'])
        publish_matching(backup_path,bounded_read(paths['journal']))
        independent_backup(backup_path,paths['journal'])
        if reference(backup_path)['sha256']!=inputs['journal']['sha256']:raise ValueError('backup SHA mismatch')
        if os.path.lexists(paths['intent']):
            intent=json.loads(bounded_read(paths['intent']),object_pairs_hook=unique_fields)
            intent_keys={'schema_version','plan_sha256','journal_sha256','backup_path','account_record',
                'observed_at','live_admission_granted'}
            if (not isinstance(intent,dict) or set(intent)!=intent_keys
                    or intent.get('schema_version')!='uid-journal-migration-intent-v1'
                    or intent.get('plan_sha256')!=reviewed_plan_sha256
                    or intent.get('journal_sha256')!=inputs['journal']['sha256']
                    or intent.get('backup_path')!=str(backup_path)
                    or intent.get('live_admission_granted') is not False):
                raise ValueError('existing migration intent differs')
            observed=datetime.fromisoformat(intent['observed_at'])
            if observed.tzinfo is None or not prepared<=observed<=clock_value(clock):
                raise ValueError('invalid original migration intent clock')
            record=intent['account_record']
        else:
            if any(os.path.lexists(paths[name]) for name in ('account_binding','account_registry')):
                raise ValueError('account owner exists without this migration intent')
            device,number=inode(paths['journal'])
            record=dict(expected,journal_device=device,journal_inode=number,verified_identity=fresh)
            intent=dict(schema_version='uid-journal-migration-intent-v1',plan_sha256=reviewed_plan_sha256,
                journal_sha256=inputs['journal']['sha256'],backup_path=str(backup_path),account_record=record,
                observed_at=clock_value(clock).isoformat(),live_admission_granted=False)
        validate_record(record,expected,journal_path=paths['journal'],policy=policy,now=clock_value(clock))
        proof=record['verified_identity']
        if (set(proof)!=set(fresh) or any(type(proof[key]) is not type(value) for key,value in fresh.items())
                or proof['live_admission_granted'] is not False or proof['ownership_lease_upgraded'] is not False
                or datetime.fromisoformat(proof['observed_at'])<prepared):
            raise ValueError('original migration identity projection differs')
        outputs=dict(intent=json_bytes(intent),account_registry=json_bytes(record),account_binding=json_bytes(record))
        # Check all existing outputs before publishing any missing one. A partial
        # publication is resumable only for this exact pinned plan and record.
        for name,content in outputs.items():
            if os.path.lexists(paths[name]) and (paths[name].is_symlink() or bounded_read(paths[name])!=content):
                raise ValueError('conflicting migration output; explicit recovery required')
        for name,content in outputs.items():
            if snapshot(paths,db,now=clock_value(clock))!=inputs:raise ValueError('source changed before publication')
            publish_matching(paths[name],content)
        if snapshot(paths,db,now=clock_value(clock))!=inputs:raise ValueError('source changed after publication')
    return dict(status='uid_binding_migrated',plan_sha256=reviewed_plan_sha256,
        journal_sha256=inputs['journal']['sha256'],backup_sha256=inputs['journal']['sha256'],
        row_count=inputs['journal']['row_count'],status_counts=inputs['journal']['status_counts'],
        live_admission_granted=False,orders_submitted=False)
