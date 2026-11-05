#!/usr/bin/env python3
"""Capture current local REST state for a retained incomplete feeder cycle."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from cryptoforge.backend import resolve_backend
from cryptoforge.feeder_selected_sync_observation import local_getter,observe_selected_sync
from database_backend import read_env


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--registration-sha256',required=True);p.add_argument('--cycle',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();target=Path(a.output).absolute();source=Path(a.root).absolute()
    if target.resolve()!=target or target.exists() or target.is_symlink() or not target.parent.is_dir() or source in target.parents:
        raise ValueError('separate canonical receipt directory required')
    env=dict(os.environ,**read_env(ROOT/'.env'));backend=resolve_backend(env)
    if backend.name!='local':raise ValueError('explicit local backend required')
    ref={'root':str(source),'manifest_sha256':a.manifest_sha256,'registration_sha256':a.registration_sha256}
    result=observe_selected_sync(ref,a.cycle,get=local_getter(backend.url,backend.key))
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(result,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'output':str(target),'pairs':len(result['observations']),'requests':result['local_rest_requests'],
                      'historical_effect':result['historical_effect'],'retry_authorized':False}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Selected-sync observation blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
