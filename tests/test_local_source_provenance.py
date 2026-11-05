from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cryptoforge.local_source_observer import bounded_process, query_sql
from cryptoforge.local_source_provenance import (
    COLUMNS, FLAGS, audit_observation, canonical, compare_observations, digest,
    freeze_contract, load_contract, migration_snapshot, parse, publish_observation,
    read_file, runtime_hashes, validate_observation,
)


NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)
ENV = dict(CRYPTOFORGE_BACKEND='local', CRYPTOFORGE_LOCAL_API_KEY='never-serialize-this-secret')


def example():
    columns = [dict(position=i, name=name, type=datatype, not_null=True, generated='',
                    identity='', collation_oid='0', default_sha256='1'*64)
               for i, (name, datatype) in enumerate(COLUMNS, 1)]
    relation = dict(schema='public', schema_oid='2200', table='market_candles', table_oid='16400',
                    kind='r', persistence='p', rls_enabled=True, rls_forced=False,
                    columns=columns, constraints=[], indexes=[], triggers=[], policies=[])
    rows = []
    for i in range(3):
        at = NOW - timedelta(minutes=15-i*5)
        body = dict(id=f'00000000-0000-0000-0000-{i+1:012d}', exchange='bybit', market_type='spot',
                    symbol='BTCUSDT', pair='BTC/USDT', timeframe='5m', open_time=at.isoformat(),
                    close_time=(at+timedelta(minutes=5)).isoformat(), open='100', high='102',
                    low='99', close='101', volume='10', turnover='1000', source='bybit_public_api',
                    ingested_at=(NOW-timedelta(days=1)).isoformat(),
                    created_at=(NOW-timedelta(days=2)).isoformat(), updated_at=NOW.isoformat())
        rows.append(dict(table_oid='16400', row_version='800', raw_json=json.dumps(body)))
    source = dict(schema_version='local-postgres-observation-v1', system_identifier='7500123412341234123',
                  database='cryptoforge', database_oid='16384', server_version_num='170006',
                  transaction_read_only='on', transaction_isolation='repeatable read',
                  database_clock=NOW.isoformat(), snapshot='800:900:', relation=relation, rows=rows)
    return dict(prepared_at=NOW.isoformat(), completed_at=(NOW+timedelta(seconds=1)).isoformat(),
                elapsed_seconds=0.9, query=dict(pair='BTC/USDT', timeframe='5m', limit=3),
                query_sha256=digest(query_sql('BTC/USDT','5m',3,NOW).encode()),runtime=runtime_hashes(),
                raw_response=json.dumps(source))


def change(observation, mutation, *, body=False, index=0):
    result = deepcopy(observation)
    source = json.loads(result['raw_response'])
    if body:
        row = json.loads(source['rows'][index]['raw_json'])
        mutation(row)
        source['rows'][index]['raw_json'] = json.dumps(row)
    else:
        mutation(source)
    result['raw_response'] = json.dumps(source)
    return result


def migration():
    return dict(schema_version='retained-local-migration-snapshot-v1',
                files={n:'2'*64 for n in ('metadata.json', 'source-hashes.json', 'verification.json', 'backup-restore-verification.json')},
                table_count=1, original_rows=3, migrated_at=(NOW-timedelta(days=2)).isoformat(),
                backup_restore_verified_at=(NOW-timedelta(days=1)).isoformat(),
                current_rows_equal_original_snapshot_verified=False, historical_row_availability_verified=False)


def register(tmp_path, *, clock=None):
    identity = validate_observation(example())['identity']
    m = migration()
    result = freeze_contract(tmp_path / 'contract', backend_env=ENV, migration=m, identity=identity,
        study_sha256='3'*64, pairs=['BTC/USDT'], start=NOW-timedelta(seconds=10), end=NOW+timedelta(days=30),
        expected_migration_sha256=digest(canonical(m)), expected_identity_sha256=digest(canonical(identity)),
        clock=clock or (lambda:NOW-timedelta(seconds=20)))
    ref = {k:result[k] for k in ('root', 'contract_sha256', 'registration_sha256')}
    contract = load_contract(ref['root'], expected_contract_sha256=ref['contract_sha256'],
                             expected_registration_sha256=ref['registration_sha256'])
    return ref, contract


def publish(tmp_path, *, contract=None, observation=None):
    return publish_observation(tmp_path / 'observation', observation=observation or example(),
                               migration=migration(), backend_env=ENV, contract=contract)


def audit(result, *, contract=None):
    return audit_observation(result['root'], expected_observation_sha256=result['observation_sha256'],
                              expected_completion_sha256=result['completion_sha256'], contract=contract)


def test_original_rows_preserved_and_imported_times_never_backdate_known_at():
    facts = validate_observation(example())
    assert len(facts['records']) == 3
    assert facts['records'][0]['row_id'].endswith('000000000001')
    assert all(r['known_at'] == (NOW+timedelta(seconds=1)).isoformat() for r in facts['records'])
    assert all(r['source_timestamp_claims']['created_at'] < r['known_at'] for r in facts['records'])
    assert facts['observation_integrity_pass'] is True
    assert all(facts[k] is False for k in FLAGS)


@pytest.mark.parametrize('mutation', [
    lambda s:s.update(transaction_read_only='off'),
    lambda s:s.update(transaction_isolation='read committed'),
    lambda s:s.update(database='wrong'),
    lambda s:s.update(system_identifier=True),
    lambda s:s.update(system_identifier='0'),
    lambda s:s.update(database_oid='-1'),
    lambda s:s.update(server_version_num='180001'),
    lambda s:s.update(database_clock=(NOW+timedelta(days=1)).isoformat()),
    lambda s:s.update(snapshot='unverified'),
    lambda s:s['relation'].update(kind='v'),
    lambda s:s['relation']['columns'][1].update(default_sha256='bad'),
    lambda s:s['relation']['columns'][0].update(type='text'),
    lambda s:s['relation'].update(columns=[]),
    lambda s:s['rows'].pop(),
    lambda s:s['rows'].append(s['rows'][0]),
    lambda s:s['rows'].reverse(),
    lambda s:s['rows'][0].update(table_oid='999'),
    lambda s:s['rows'][0].update(row_version='0'),
    lambda s:s['rows'][0].update(extra='bad'),
])
def test_bad_snapshot_and_original_inventory_rejected(mutation):
    with pytest.raises(ValueError):
        validate_observation(change(example(), mutation))


@pytest.mark.parametrize('mutation', [
    lambda r:r.update(market_type='linear'),
    lambda r:r.update(pair='ETH/USDT'),
    lambda r:r.update(symbol='ETHUSDT'),
    lambda r:r.update(source='unknown'),
    lambda r:r.update(timeframe='15m'),
    lambda r:r.update(id='invalid'),
    lambda r:r.update(secret='must-not-enter-evidence'),
    lambda r:r.update(open='NaN'),
    lambda r:r.update(open='0'),
    lambda r:r.update(low='103'),
    lambda r:r.update(volume='-1'),
    lambda r:r.update(created_at=(NOW+timedelta(days=1)).isoformat()),
    lambda r:r.update(updated_at=(NOW+timedelta(days=1)).isoformat()),
    lambda r:r.update(ingested_at=(NOW+timedelta(days=1)).isoformat()),
    lambda r:r.update(close_time=(NOW+timedelta(minutes=5)).isoformat()),
    lambda r:r.update(open_time=(NOW-timedelta(minutes=14)).isoformat()),
    lambda r:r.update(open_time=(NOW-timedelta(minutes=20)).isoformat(), close_time=(NOW-timedelta(minutes=15)).isoformat()),
])
def test_bad_future_gapped_and_unqualified_source_rows_rejected(mutation):
    with pytest.raises(ValueError):
        validate_observation(change(example(), mutation, body=True))


@pytest.mark.parametrize('key,value', [('elapsed_seconds',float('nan')), ('elapsed_seconds',True),
                                     ('elapsed_seconds',16), ('completed_at',(NOW-timedelta(seconds=1)).isoformat()),
                                     ('completed_at',(NOW+timedelta(hours=1)).isoformat())])
def test_original_clock_budget_rejected(key, value):
    observation = example(); observation[key] = value
    with pytest.raises(ValueError):validate_observation(observation)


def test_duplicate_json_keys_in_original_response_and_row_rejected():
    observation = example()
    observation['raw_response'] = observation['raw_response'].replace('"database": "cryptoforge"', '"database": "cryptoforge", "database": "cryptoforge"')
    with pytest.raises(ValueError, match='duplicate'):validate_observation(observation)
    observation = example(); source=json.loads(observation['raw_response'])
    source['rows'][0]['raw_json']=source['rows'][0]['raw_json'].replace('"open": "100"', '"open": "100", "open": "100"')
    observation['raw_response']=json.dumps(source)
    with pytest.raises(ValueError, match='duplicate'):validate_observation(observation)


def test_numeric_lexemes_are_hashed_as_original_bytes_without_float_roundtrip():
    observation=example();source=json.loads(observation['raw_response'])
    raw=source['rows'][0]['raw_json'].replace('"turnover": "1000"','"turnover": 1234567890.123456789012')
    source['rows'][0]['raw_json']=raw; observation['raw_response']=json.dumps(source)
    assert validate_observation(observation)['records'][0]['raw_row_sha256']==digest(raw.encode())


def test_offline_sealed_probe_and_credentials_not_serialized(tmp_path, monkeypatch):
    result=publish(tmp_path)
    monkeypatch.setenv('CRYPTOFORGE_BACKEND','supabase')
    monkeypatch.setattr('cryptoforge.local_source_provenance.resolve_backend',lambda env:(_ for _ in ()).throw(AssertionError('offline reader connected')))
    checked=audit(result)
    assert checked['rows_checked']==3 and checked['original_source_snapshot_integrity_pass'] is True
    assert all(checked[k] is False for k in FLAGS)
    assert ENV['CRYPTOFORGE_LOCAL_API_KEY'] not in (tmp_path/'observation/observation.json').read_text()


def test_prospective_contract_and_registered_observation(tmp_path):
    ref,contract=register(tmp_path)
    result=publish(tmp_path,contract=ref)
    assert audit(result,contract=ref)['scope']=='registered_source_observation'
    assert contract['backend']['transport']=='local_docker_postgres_read_only'
    with pytest.raises(ValueError):audit(result)


@pytest.mark.parametrize('field', ['system_identifier','database_oid','relation_sha256','server_version_num'])
def test_wrong_actual_instance_schema_or_version_cannot_match_contract(tmp_path, field):
    ref,_=register(tmp_path)
    if field=='relation_sha256':
        changed=change(example(),lambda s:s['relation']['columns'][1].update(default_sha256='a'*64))
    else:
        changed=change(example(),lambda s:s.update({field: {'system_identifier':'7500123412341234124','database_oid':'16385','server_version_num':'170007'}[field]}))
    with pytest.raises(ValueError,match='contract differs'):publish(tmp_path,contract=ref,observation=changed)
    assert not (tmp_path/'observation').exists()


def test_probe_cannot_be_adopted_into_later_registered_window(tmp_path):
    original=publish(tmp_path)
    ref,_=register(tmp_path)
    with pytest.raises(ValueError,match='diagnostic'):audit(original,contract=ref)


@pytest.mark.parametrize('calls', [
    [NOW-timedelta(seconds=20),NOW,NOW,NOW],
    [NOW-timedelta(seconds=20),NOW-timedelta(seconds=20),NOW,NOW],
    [NOW-timedelta(seconds=20)]*3+[NOW],
])
def test_late_registration_never_produces_adoptable_ready(tmp_path,calls):
    ticks=iter(calls)
    with pytest.raises(ValueError,match='missed'):register(tmp_path,clock=lambda:next(ticks))
    assert not (tmp_path/'contract/registered.json').exists()


def test_original_files_and_partial_roots_cannot_be_overwritten(tmp_path):
    result=publish(tmp_path);before=read_file(tmp_path/'observation/observation.json')
    with pytest.raises(FileExistsError):publish(tmp_path)
    assert read_file(tmp_path/'observation/observation.json')==before
    (tmp_path/'observation/complete.json').unlink()
    with pytest.raises((ValueError,FileNotFoundError)):audit(result)


def test_hardlink_symlink_and_wrong_external_pins_rejected(tmp_path):
    result=publish(tmp_path)
    with pytest.raises(ValueError):audit_observation(result['root'],expected_observation_sha256='0'*64,expected_completion_sha256=result['completion_sha256'])
    (tmp_path/'other').hardlink_to(tmp_path/'observation/observation.json')
    with pytest.raises(ValueError,match='single|private'):audit(result)
    (tmp_path/'other').unlink()
    (tmp_path/'alias').symlink_to(tmp_path/'observation',target_is_directory=True)
    bad={**result,'root':str(tmp_path/'alias')}
    with pytest.raises(ValueError):audit(bad)


def test_rehashed_backdated_derived_known_at_rejected(tmp_path):
    result=publish(tmp_path);path=tmp_path/'observation/observation.json';value=parse(path.read_bytes())
    value['derived']['records'][0]['known_at']=(NOW-timedelta(days=10)).isoformat()
    raw=canonical(value);path.write_bytes(raw)
    ready=canonical(dict(observation_sha256=digest(raw)));(path.parent/'complete.json').write_bytes(ready)
    result.update(observation_sha256=digest(raw),completion_sha256=digest(ready))
    with pytest.raises(ValueError,match='known_at'):audit(result)


def later(observation):
    result=deepcopy(observation)
    result['prepared_at']=(NOW+timedelta(seconds=2)).isoformat()
    result['completed_at']=(NOW+timedelta(seconds=3)).isoformat()
    result['query_sha256']=digest(query_sql(**result['query'],cutoff=NOW+timedelta(seconds=2)).encode())
    return result


def test_changed_row_revision_gets_new_observation_time_and_preserves_old():
    first=example();before=canonical(first)
    next=change(later(first),lambda r:r.update(close='100.5'),body=True)
    result=compare_observations(first,next)
    assert result['rows'][0]['status']=='revised'
    assert result['rows'][1]['status']=='unchanged'
    assert result['rows'][0]['known_at']==(NOW+timedelta(seconds=3)).isoformat()
    assert canonical(first)==before
    assert result['source_poll_completeness_verified'] is False


def test_reinserted_candle_id_and_wrong_source_comparison_rejected():
    with pytest.raises(ValueError,match='different original row ID'):
        compare_observations(example(),change(later(example()),lambda r:r.update(id='11111111-1111-1111-1111-111111111111'),body=True))
    with pytest.raises(ValueError,match='ordering'):
        compare_observations(example(),example())
    with pytest.raises(ValueError,match='source/schema'):
        compare_observations(example(),change(later(example()),lambda s:s.update(system_identifier='7500123412341234124')))


def migration_files(tmp_path):
    source=[dict(table_name='public.market_candles',rows=3,content_hash='a'*32)]
    verification=dict(verified_at=(NOW-timedelta(days=1)).isoformat(),all_tables_match=True,
                      table_count=1,total_rows=3,tables=source)
    values={'source-hashes.json':source,'metadata.json':dict(tables=[dict(schema='public',name='market_candles')]),
            'verification.json':verification,'backup-restore-verification.json':verification}
    for name,value in values.items():(tmp_path/name).write_text(json.dumps(value))


def test_migration_snapshot_retains_original_file_hashes_without_claiming_current_equality(tmp_path):
    migration_files(tmp_path);snapshot=migration_snapshot(tmp_path)
    assert snapshot['original_rows']==3 and snapshot['table_count']==1
    assert snapshot['files']['metadata.json']==digest((tmp_path/'metadata.json').read_bytes())
    assert snapshot['current_rows_equal_original_snapshot_verified'] is False


@pytest.mark.parametrize('target', ['source-hashes.json','verification.json','backup-restore-verification.json','metadata.json'])
def test_migration_inventory_and_restore_disagreement_rejected(tmp_path,target):
    migration_files(tmp_path);p=tmp_path/target;j=json.loads(p.read_text())
    if target=='source-hashes.json':j.append(j[0])
    elif target=='metadata.json':j['tables'].append(j['tables'][0])
    else:j['all_tables_match']=False
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError):migration_snapshot(tmp_path)


@pytest.mark.parametrize('pair,timeframe,limit',[("BTC/USDT'; DROP TABLE x;--",'5m',3),('BTC/USDT','5m; DELETE',3),('BTC/USDT','5m',True),('BTC/USDT','5m',121)])
def test_query_cannot_be_extended_with_sql(pair,timeframe,limit):
    with pytest.raises(ValueError):query_sql(pair,timeframe,limit,NOW)


def test_query_is_bounded_repeatable_read_and_rollback_only():
    sql=query_sql('BTC/USDT','5m',120,NOW)
    assert sql.startswith('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;')
    assert sql.rstrip().endswith('ROLLBACK;')
    assert "statement_timeout = '2000ms'" in sql and "lock_timeout = '250ms'" in sql
    assert 'LIMIT 120' in sql and 'OFFSET' not in sql and 'pg_control_system' in sql
    assert not any(word in sql for word in ('INSERT INTO','UPDATE public','DELETE FROM','CREATE TABLE','ALTER TABLE','COMMIT;'))


def test_process_stdout_and_stderr_budgets_and_exit_are_guarded():
    assert bounded_process([sys.executable,'-c',"print('ok')"],'',maximum_bytes=100,maximum_seconds=2)==b'ok\n'
    for script in ["print('x'*10000)","import sys;sys.stderr.write('SECRET');sys.exit(1)"]:
        with pytest.raises(ValueError) as error:
            bounded_process([sys.executable,'-c',script],'',maximum_bytes=100,maximum_seconds=2)
        assert 'SECRET' not in str(error.value)


def test_process_timeout_kills_stalled_reader():
    with pytest.raises(ValueError,match='timed out'):
        bounded_process([sys.executable,'-c','import time;time.sleep(30)'],'',maximum_bytes=100,maximum_seconds=1)


def test_stale_diagnostic_is_preserved_but_cannot_be_used_in_registered_source(tmp_path):
    stale=example()
    stale['prepared_at']=(NOW+timedelta(hours=14)).isoformat()
    stale['completed_at']=(NOW+timedelta(hours=14,seconds=1)).isoformat()
    stale['query_sha256']=digest(query_sql(**stale['query'],cutoff=NOW+timedelta(hours=14)).encode())
    stale=change(stale,lambda s:s.update(database_clock=(NOW+timedelta(hours=14)).isoformat()))
    facts=validate_observation(stale)
    assert facts['observation_integrity_pass'] is True and facts['candle_freshness_pass'] is False
    diagnostic=publish(tmp_path/'diagnostic',observation=stale)
    assert audit(diagnostic)['candle_freshness_pass'] is False
    ref,_=register(tmp_path)
    with pytest.raises(ValueError,match='contract differs'):publish(tmp_path,contract=ref,observation=stale)


def test_rls_definition_drift_changes_schema_identity():
    policy=dict(name='test_policy',command='r',permissive=True,roles='{0}',using_sha256='a'*64,check_sha256='b'*64)
    original=change(example(),lambda s:s['relation'].update(policies=[policy]))
    changed=change(later(original),lambda s:s['relation']['policies'][0].update(using_sha256='c'*64))
    with pytest.raises(ValueError,match='source/schema'):compare_observations(original,changed)


def test_production_database_directories_cannot_receive_new_evidence():
    project=Path(__file__).resolve().parents[1]
    for parent in ['.local/database','.local/database-transfer']:
        path=project/parent/'must-not-create-source-evidence'
        with pytest.raises(ValueError,match='separate'):publish_observation(path,observation=example(),migration=migration(),backend_env=ENV)
        assert not path.exists()


@pytest.mark.parametrize('field',['runtime','query_sha256'])
def test_observation_runtime_or_original_query_drift_is_rejected(field):
    observation=example()
    observation[field] = {'backend.py':'a'*64} if field=='runtime' else 'a'*64
    with pytest.raises(ValueError,match='runtime/query'):validate_observation(observation)


def test_loaded_runtime_drift_during_query_never_exposes_a_snapshot(tmp_path,monkeypatch):
    from cryptoforge import local_source_provenance as provenance
    from cryptoforge.local_source_observer import LocalPostgresObserver
    source=provenance._RUNTIME_PATHS['backend.py'];copy=tmp_path/'backend-copy.py';copy.write_bytes(source.read_bytes())
    monkeypatch.setitem(provenance._RUNTIME_PATHS,'backend.py',copy)
    def changed(*args,**kwargs):
        copy.write_text('changed-during-read')
        return b'{}'
    monkeypatch.setattr('cryptoforge.local_source_observer.bounded_process',changed)
    with pytest.raises(ValueError,match='runtime changed'):
        LocalPostgresObserver(Path(__file__).resolve().parents[1]).read(pair='BTC/USDT',limit=3)


def test_uuid_reused_after_window_shift_is_not_a_new_candle():
    current=deepcopy(example())
    current['prepared_at']=(NOW+timedelta(minutes=5)).isoformat()
    current['completed_at']=(NOW+timedelta(minutes=5,seconds=1)).isoformat()
    current['query_sha256']=digest(query_sql(**current['query'],cutoff=NOW+timedelta(minutes=5)).encode())
    source=json.loads(current['raw_response'])
    source['database_clock']=current['prepared_at']
    reused=source['rows'][0]
    body=json.loads(reused['raw_json']);body.update(open_time=NOW.isoformat(),close_time=(NOW+timedelta(minutes=5)).isoformat())
    reused['raw_json']=json.dumps(body)
    source['rows']=source['rows'][1:]+[reused]
    current['raw_response']=json.dumps(source)
    with pytest.raises(ValueError,match='UUID moved'):compare_observations(example(),current)


def test_cli_has_no_as_of_override_and_offline_audit_without_database(tmp_path):
    result=publish(tmp_path)
    script=Path(__file__).resolve().parents[1]/'scripts/audit_local_source_provenance.py'
    p=subprocess.run([sys.executable,str(script),'audit','--root',result['root'],
                      '--observation-sha256',result['observation_sha256'],'--completion-sha256',result['completion_sha256']],
                      capture_output=True,text=True,timeout=10)
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['rows_checked']==3
    assert 'never-serialize' not in p.stdout+p.stderr
    p=subprocess.run([sys.executable,str(script),'probe','--output',str(tmp_path/'bad'),'--as-of',NOW.isoformat()],capture_output=True,text=True,timeout=10)
    assert p.returncode==2 and not (tmp_path/'bad').exists()
