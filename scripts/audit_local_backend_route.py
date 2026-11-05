"""Read-only local api/rest/db and closed-row linkage; no migrations or orders."""
from datetime import UTC, datetime
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from database_backend import read_env
from cryptoforge.local_source_provenance import canonical,digest,_new_root,_write_new
from cryptoforge.local_backend_route import observe_backend_route


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pair',choices=('BTC/USDT','ETH/USDT'),default='BTC/USDT')
    args=p.parse_args(argv)
    names=('local_backend_route.py','backend.py','local_source_provenance.py','local_source_observer.py')
    paths={n:ROOT/'src/cryptoforge'/n for n in names}
    paths.update({n:ROOT/'scripts'/n for n in ('database_backend.py','audit_local_backend_route.py')})
    paths.update({n:ROOT/'docker'/n for n in ('database.compose.yml','database-nginx.conf')})
    runtime={n:digest(path.read_bytes()) for n,path in paths.items()}
    env=dict(os.environ,**read_env(ROOT/'.env'))
    observation=observe_backend_route(ROOT,env,pair=args.pair)
    if runtime!={n:digest(path.read_bytes()) for n,path in paths.items()}:
        raise ValueError('local route runtime changed during capture')
    observation['runtime']=runtime
    root=_new_root(args.output)
    pin=_write_new(root/'observation.json',observation)
    completed=_write_new(root/'complete.json',dict(observation_sha256=pin,completed_at=datetime.now(UTC).isoformat()))
    sys.stdout.buffer.write(canonical(dict(root=str(root),observation_sha256=pin,completion_sha256=completed,
        rest_instance_identity_verified=True,row_binding=observation['row_binding'],
        full_worker_or_host_qualified=False,live_admission_granted=False))+b'\n')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Local route observation failed: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
