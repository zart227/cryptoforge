"""Compare bounded, sanitized observations; never attribute a database write."""
from datetime import UTC,datetime
import re
from pathlib import Path

from cryptoforge.local_source_provenance import digest,parse,read_file,stamp


def _pairs(value):
    if (not isinstance(value,list) or len(value)>20 or
            any(not isinstance(x,str) or not re.fullmatch('[A-Z0-9]{1,24}/USDT',x) for x in value) or
            len(set(value))!=len(value)):
        raise ValueError('bounded unique Spot pairs required')
    return value


def _pinned(path,pin):
    path=Path(path).absolute()
    if path.resolve()!=path or not re.fullmatch('[a-f0-9]{64}',str(pin)):
        raise ValueError('canonical pinned observation required')
    raw=read_file(path,maximum=65536)
    if digest(raw)!=pin:raise ValueError('observation hash mismatch')
    return path,raw,parse(raw)


def compare_writers(host_path,host_sha256,selected_path,selected_sha256,*,get,clock=None):
    """Compare one filtered service log to one current local health row.

    The journal window and prior REST capture are separate observations. Exact
    pair matches are consistent with a shared source, not a provenance proof.
    """
    clock=clock or (lambda:datetime.now(UTC));started=stamp(clock())
    hp,host_raw,host=_pinned(host_path,host_sha256)
    sp,selection_raw,selection=_pinned(selected_path,selected_sha256)
    if host.get('services_changed') is not False or host.get('database_modified') is not False:
        raise ValueError('read-only host observation required')
    lines=host.get('training_journal_synced_pairs','').splitlines()
    if len(lines)!=1 or not lines[0].startswith('synced_pairs='):
        raise ValueError('single filtered training sync line required')
    text=lines[0].partition('=')[2]
    training=_pairs(text.split(',') if text else [])
    if not training:raise ValueError('nonempty training sync line required')
    if (selection.get('historical_effect')!='unknown' or selection.get('retry_authorized') is not False or
            not isinstance(selection.get('observations'),list)):
        raise ValueError('original selected-sync observation required')
    selected=_pairs([row['pair'] for row in selection['observations']])
    if not selected:raise ValueError('selected pair observation required')
    rows,pin=get('bot_health',{'component':'eq.supabase_market_sync',
                               'select':'component,status,observed_at,payload','limit':'1'})
    if not isinstance(rows,list) or len(rows)>1 or not re.fullmatch('[a-f0-9]{64}',str(pin)):
        raise ValueError('bounded local health response required')
    current=None
    if rows:
        row=rows[0]
        if (not isinstance(row,dict) or set(row)!={'component','status','observed_at','payload'} or
                row['component']!='supabase_market_sync' or row['status'] not in ('ok','warning','error','critical') or
                not isinstance(row['payload'],dict)):
            raise ValueError('expected projected health row required')
        when=stamp(row['observed_at'])
        if when>started:raise ValueError('future health timestamp')
        payload=row['payload'];synced=_pairs(payload.get('synced_pairs',[]));requested=_pairs(payload.get('pairs',[]))
        failed=payload.get('failed',{})
        if not isinstance(failed,dict) or len(failed)>20:raise ValueError('bounded failure map required')
        if not set(synced)<=set(requested):raise ValueError('health synced pairs outside request')
        current={'status':row['status'],'observed_at':when.isoformat(),'requested_pair_count':len(requested),
                 'synced_pair_count':len(synced),'failed_pair_count':len(failed),
                 'training_journal_exact_sync_list_match':synced==training,
                 'selected_and_health_synced_overlap':sorted(set(selected)&set(synced)),
                 'selected_and_health_requested_overlap':sorted(set(selected)&set(requested))}
    if digest(read_file(hp,maximum=65536))!=digest(host_raw) or digest(read_file(sp,maximum=65536))!=digest(selection_raw):
        raise ValueError('source observation changed during comparison')
    completed=stamp(clock())
    if completed<started:raise ValueError('observation clock moved backwards')
    return {'schema_version':'feeder-competing-writers-v1','started_at':started.isoformat(),'completed_at':completed.isoformat(),
            'host_observation_sha256':host_sha256,'selected_observation_sha256':selected_sha256,
            'training_journal_pair_count':len(training),'selected_pair_count':len(selected),
            'training_and_selected_overlap':sorted(set(training)&set(selected)),
            'current_local_health':current,'health_response_sha256':pin,'raw_health_response_retained':False,
            'journal_entry_timestamp_retained':False,'database_instance_binding_proved':False,
            'writer_attribution_proved':False,'historical_selected_sync_effect':'unknown',
            'retry_authorized':False,'database_modified':False,
            'scope':'cross-observation consistency only, not causal database provenance'}
