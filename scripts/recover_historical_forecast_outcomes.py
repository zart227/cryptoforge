"""One-off bounded recovery of a frozen historical diagnostic backlog."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'src'))

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.primary_forecast_outcomes import BybitPrimaryEndpointReader
from scripts.collect_primary_forecast_outcomes import original_policy_resolver


def freeze(memory, directory, *, now):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory/'manifest.json'
    if manifest.exists():
        result = json.loads(manifest.read_text())
        if result['ledger'] != str(memory.path.resolve()):
            raise ValueError('recovery ledger mismatch')
        return result
    if shutil.disk_usage(directory).free < (2048*1024**2 + memory.path.stat().st_size):
        raise ValueError('backup must preserve disk reserve')
    backup = directory/'before.sqlite'
    if backup.exists():
        raise ValueError('incomplete recovery initialization requires inspection')
    with closing(sqlite3.connect(memory.path.as_uri()+'?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(backup)) as dest:
            source.backup(dest)
    backup.chmod(0o600)
    with closing(sqlite3.connect(backup.as_uri()+'?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('invalid recovery backup')
        has_outcomes=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='primary_forecast_outcomes'").fetchone()
        missing='NOT EXISTS(SELECT 1 FROM primary_forecast_outcomes o WHERE o.forecast=f.id)' if has_outcomes else '1'
        rows = db.execute(f'''SELECT f.id,f.payload FROM primary_forecasts f
            WHERE {missing}
            AND json_extract(f.payload,'$.target_information_end')<?
            ORDER BY json_extract(f.payload,'$.target_information_end'),f.id LIMIT 1001''',
            ((now-timedelta(hours=36)).isoformat(),)).fetchall()
        if len(rows)>1000:
            raise ValueError('historical recovery bounded to 1000 forecasts')
    result = {'ledger': str(memory.path.resolve()), 'frozen_at': now.isoformat(),
              'forecasts': [{'forecast_id': key, 'payload': json.loads(raw),
                            'payload_sha256': hashlib.sha256(raw.encode()).hexdigest()} for key,raw in rows]}
    write_json_report(manifest,result)
    return result


def recover_batch(memory, directory, manifest, endpoint_reader, *, policy_resolver=None,
                  maximum_forecasts=40, wall_seconds=45, monotonic=time.monotonic):
    if not 1<=maximum_forecasts<=100 or not 0<wall_seconds<=60:
        raise ValueError('bounded historical recovery required')
    started=monotonic();counts=Counter();attempted=0
    for item in manifest['forecasts']:
        key=item['forecast_id']; forecast=item['payload']
        if memory.available_outcome(key,as_of=memory.clock()) is not None:
            counts['already_resolved']+=1;continue
        if attempted>=maximum_forecasts or monotonic()-started>=wall_seconds:
            counts['deferred']+=1;continue
        attempted+=1;receipt={'forecast_id':key,'pair':forecast['pair'],
            'target_information_end':forecast['target_information_end'],
            'source':'bybit_public_spot_kline','historical_availability_claimed':False}
        output=directory/'receipts'/(key+'.json')
        try:
            with closing(sqlite3.connect(memory.path.as_uri()+'?mode=ro',uri=True)) as db:
                current=db.execute('SELECT payload FROM primary_forecasts WHERE id=?',(key,)).fetchone()
            if current is None or hashlib.sha256(current[0].encode()).hexdigest()!=item['payload_sha256']:
                raise ValueError('original forecast changed or missing')
            candle=endpoint_reader.read_target_candle(forecast['pair'],target=datetime.fromisoformat(forecast['target_information_end']))
            if candle is None:
                receipt['status']='missing_exact_target_candle'
            else:
                receipt['candle']={'open_time':candle.open_time.isoformat(),
                    'observed_at':candle.cache_observed_at.isoformat(),
                    **{name:str(getattr(candle,name)) for name in ('open','high','low','close','volume')}}
                # Persist evidence before writing an outcome; interruption can be audited.
                receipt['status']='evidence_observed_before_outcome'
                write_json_report(output,receipt)
                policy=policy_resolver(forecast['artifact_sha256']) if policy_resolver and forecast.get('label_policy_known') is not True else None
                receipt.update(memory.record_outcome(key,candle,original_policy=policy))
        except Exception as exc:
            receipt.update(status='recovery_error',error_type=type(exc).__name__)
            if isinstance(exc,ValueError):receipt['reason']=str(exc)
        counts[receipt['status']]+=1
        write_json_report(output,receipt)
    remaining=[r['forecast_id'] for r in manifest['forecasts'] if memory.available_outcome(r['forecast_id'],as_of=memory.clock()) is None]
    report={'observed_at':memory.clock().isoformat(),'frozen_forecasts':len(manifest['forecasts']),
        'remaining':remaining,'remaining_count':len(remaining),'resolved_count':len(manifest['forecasts'])-len(remaining),
        'attempted_this_pass':attempted,'counts':dict(counts),'wall_seconds':monotonic()-started,
        'cash_training_rows_added':0,'live_promotion_allowed':False,'historical_availability_claimed':False}
    write_json_report(directory/'latest.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--maximum-forecasts',type=int,default=40)
    parser.add_argument('--wall-seconds',type=float,default=45)
    args=parser.parse_args()
    path=Path(os.environ.get('CRYPTOFORGE_PRIMARY_FORECAST_LEDGER','.local/state/primary-forecast-memory.sqlite')).resolve()
    memory=PrimaryForecastMemory.from_env(path)
    import fcntl
    args.directory.mkdir(parents=True,exist_ok=True)
    with (args.directory/'recovery.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=freeze(memory,args.directory.resolve(),now=datetime.now(UTC))
        report=recover_batch(memory,args.directory.resolve(),manifest,
            BybitPrimaryEndpointReader(BybitPublicClient(timeout=3,max_retries=0)),
            policy_resolver=original_policy_resolver(Path('.local/models')),
            maximum_forecasts=args.maximum_forecasts,wall_seconds=args.wall_seconds)
    print(json.dumps({k:v for k,v in report.items() if k!='remaining'}))


if __name__=='__main__':main()
