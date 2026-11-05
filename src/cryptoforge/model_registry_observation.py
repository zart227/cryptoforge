"""Observe two projected local model events, never perform model activation."""
from datetime import UTC,datetime
import hashlib
from pathlib import Path
import re
from urllib import parse,request

from cryptoforge.local_source_provenance import digest,parse as parse_json,read_file,stamp


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def model_event_getter(url,key,*,timeout=3,maximum_bytes=65536):
    parsed=parse.urlsplit(url)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1') or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path not in ('','/') or not key):
        raise ValueError('numeric loopback origin required')
    opener=request.build_opener(request.ProxyHandler({}),_NoRedirect());origin=url.rstrip('/')
    def get(event_type):
        if event_type not in ('model.active','model.candidate'):raise ValueError('model event allowlist required')
        query={'event_type':'eq.'+event_type,'select':'occurred_at,model_version:payload->>model_version,trained_at:payload->artifact->>trained_at,artifact_sha256:payload->>artifact_sha256',
               'order':'occurred_at.desc','limit':'1'}
        req=request.Request(origin+'/rest/v1/system_events?'+parse.urlencode(query),
                            headers={'apikey':key,'Authorization':'Bearer '+key},method='GET')
        with opener.open(req,timeout=timeout) as resp:
            if resp.status!=200:raise ValueError('local model event read failed')
            raw=resp.read(maximum_bytes+1)
        if len(raw)>maximum_bytes:raise ValueError('model event byte limit')
        rows=parse_json(raw)
        if not isinstance(rows,list) or len(rows)>1:raise ValueError('bounded model event required')
        return rows,hashlib.sha256(raw).hexdigest()
    return get


def observe_model_registry(audit_path,audit_sha256,*,get,clock=None):
    clock=clock or (lambda:datetime.now(UTC));started=stamp(clock())
    path=Path(audit_path).absolute()
    if path.resolve()!=path or not re.fullmatch('[a-f0-9]{64}',str(audit_sha256)):
        raise ValueError('canonical pinned training audit required')
    raw=read_file(path,maximum=65536)
    if digest(raw)!=audit_sha256:raise ValueError('training audit hash mismatch')
    audit=parse_json(raw)
    if (audit.get('schema_version')!='model-training-journal-audit-v1' or
            audit.get('executed_cash_profit_established') is not False or audit.get('orders_placed') is not False):
        raise ValueError('price training audit required')
    events={}
    for kind in ('model.active','model.candidate'):
        rows,pin=get(kind)
        if not isinstance(rows,list) or len(rows)>1 or not re.fullmatch('[a-f0-9]{64}',str(pin)):
            raise ValueError('bounded model event response required')
        value=None
        if rows:
            row=rows[0]
            if not isinstance(row,dict) or set(row)!={'occurred_at','model_version','trained_at','artifact_sha256'}:
                raise ValueError('model event projection differs')
            version=row['model_version'];sha=row['artifact_sha256'];trained=row['trained_at']
            if (not isinstance(version,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,160}',version) or
                    (sha is not None and (not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha)))):
                raise ValueError('bounded model identity required')
            occurred=stamp(row['occurred_at'])
            if occurred>started:raise ValueError('future model event')
            if trained is not None:
                trained=stamp(trained)
                if trained>occurred:raise ValueError('model trained after event')
            value={'occurred_at':occurred.isoformat(),'model_version':version,
                   'trained_at':trained.isoformat() if trained is not None else None,'artifact_sha256':sha}
        events[kind]={'event':value,'response_sha256':pin}
    if digest(read_file(path,maximum=65536))!=audit_sha256:raise ValueError('training audit changed')
    completed=stamp(clock())
    if completed<started:raise ValueError('observation clock moved backwards')
    active=events['model.active']['event'];candidate=events['model.candidate']['event']
    return {'schema_version':'local-model-registry-observation-v1','started_at':started.isoformat(),
            'completed_at':completed.isoformat(),'training_audit_sha256':audit_sha256,'events':events,
            'active_event_matches_training_incumbent':active['model_version']==audit.get('incumbent_model_version') if active else None,
            'latest_candidate_event_matches_training_candidate':candidate['model_version']==audit.get('candidate_model_version') if candidate else None,
            'database_instance_binding_proved':False,'active_executor_loaded_model_proved':False,
            'current_incumbent_comparison_established':False,'executed_cash_profit_established':False,
            'database_modified':False,'orders_placed':False,
            'scope':'two current local registry event projections; no runtime or performance qualification'}
