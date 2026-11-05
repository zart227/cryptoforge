#!/usr/bin/env python3
"""Compare retained service evidence with current local health, read-only."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from cryptoforge.backend import resolve_backend
from cryptoforge.feeder_competing_writers import compare_writers
from cryptoforge.feeder_selected_sync_observation import local_getter
from database_backend import read_env


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',required=True);p.add_argument('--host-sha256',required=True)
    p.add_argument('--selected',required=True);p.add_argument('--selected-sha256',required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    target=Path(a.output).absolute()
    if target.resolve()!=target or target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError('new canonical report required')
    backend=resolve_backend(dict(os.environ,**read_env(ROOT/'.env')))
    if backend.name!='local':raise ValueError('explicit local backend required')
    r=compare_writers(a.host,a.host_sha256,a.selected,a.selected_sha256,get=local_getter(backend.url,backend.key))
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'output':str(target),'training_and_selected_overlap':r['training_and_selected_overlap'],
                      'current_local_health':r['current_local_health'],'writer_attribution_proved':False}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Competing-writer observation blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
