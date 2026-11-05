#!/usr/bin/env python3
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from cryptoforge.backend import resolve_backend
from cryptoforge.model_registry_observation import model_event_getter,observe_model_registry
from database_backend import read_env


def main():
    p=argparse.ArgumentParser();p.add_argument('--audit',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).absolute()
    if out.resolve()!=out or out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('new canonical output required')
    backend=resolve_backend(dict(os.environ,**read_env(ROOT/'.env')))
    if backend.name!='local':raise ValueError('explicit local backend required')
    result=observe_model_registry(a.audit,a.sha256,get=model_event_getter(backend.url,backend.key))
    fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'output':str(out),'events':{k:v['event'] for k,v in result['events'].items()},
                      'active_event_matches_training_incumbent':result['active_event_matches_training_incumbent'],
                      'active_executor_loaded_model_proved':False}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Local model event observation blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
