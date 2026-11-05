"""Register, run, inspect or prepare a bounded local market-feeder user service."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from database_backend import read_env
from cryptoforge.local_source_provenance import canonical,parse,read_file,_new_root,_write_new,digest
from cryptoforge.managed_reference_feeder import ManagedReferenceFeeder


def _env():
    value=dict(os.environ,**read_env(ROOT/'.env'),PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1')
    bypass=','.join(filter(None,(value.get('no_proxy',value.get('NO_PROXY','')),'127.0.0.1,localhost,::1')))
    value.update(no_proxy=bypass,NO_PROXY=bypass);return value


def _quote(value):
    if any(c in value for c in '\n\r\x00'):raise ValueError('single-line unit value required')
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'


def service_text(reference):
    argv=[sys.executable,str(ROOT/'scripts/manage_reference_feeder.py'),'run','--root',reference['root'],
        '--manifest-sha256',reference['manifest_sha256'],'--registration-sha256',reference['registration_sha256']]
    return '[Unit]\nDescription=CryptoForge reference-aware local market feeder\n\n[Service]\nType=oneshot\n'+\
        'WorkingDirectory='+str(ROOT).replace('%','%%')+'\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nExecStart='+\
        ' '.join(_quote(a) for a in argv)+'\nTimeoutStartSec=420\nKillMode=control-group\nUMask=0077\nNoNewPrivileges=yes\nMemoryMax=768M\nTasksMax=64\n'


TIMER='''[Unit]
Description=Refresh mandatory references and selected market pairs after each cycle

[Timer]
OnBootSec=30s
OnUnitInactiveSec=120s
AccuracySec=1s
Unit=cryptoforge-market-feeder.service

[Install]
WantedBy=timers.target
'''


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('register');s.add_argument('--root',type=Path,required=True)
    for name in ('run','status','propose-service'):
        s=sub.add_parser(name);s.add_argument('--root',type=Path,required=True)
        s.add_argument('--manifest-sha256',required=True);s.add_argument('--registration-sha256',required=True)
        if name=='propose-service':s.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='register':
        obj=ManagedReferenceFeeder.create(args.root,ROOT,_env());result=obj.status()
    else:
        ref=dict(root=str(args.root.absolute()),manifest_sha256=args.manifest_sha256,registration_sha256=args.registration_sha256)
        obj=ManagedReferenceFeeder.open(ref)
        if args.command=='run':result=obj.run(_env())
        elif args.command=='status':result=obj.status()
        else:
            root=_new_root(args.output)
            for name,body in [('cryptoforge-market-feeder.service',service_text(ref)),('cryptoforge-market-feeder.timer',TIMER)]:
                path=root/name;path.write_text(body);path.chmod(0o600)
            result=dict(root=str(root),reference=ref,service_sha256=digest((root/'cryptoforge-market-feeder.service').read_bytes()),timer_sha256=digest(TIMER.encode()),installed=False)
    sys.stdout.buffer.write(canonical(result)+b'\n')
    return 0 if args.command!='run' or result['success'] else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # Only fixed local guard messages are safe to expose; network errors may
        # contain credentials or response bodies.
        reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
            'incomplete operational cycle requires explicit investigation',
            'owned managed feeder contract/runtime changed',
            'managed feeder runtime changed',
            'protected operational retention budget exhausted',
            'managed feeder disk reserve preserved',
        } else type(exc).__name__
        print('Managed reference feeder failed: '+reason,file=sys.stderr);raise SystemExit(1)
