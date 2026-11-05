#!/usr/bin/env python3
import argparse,json,os
from pathlib import Path
from cryptoforge.model_training_journal_audit import audit_training_journal


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output).absolute()
    if out.resolve()!=out or out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('new canonical output required')
    report=audit_training_journal(a.input,a.sha256)
    fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'output':str(out),'candidate':report['candidate_model_version'],'promotion':report['promotion'],
                      'executed_cash_profit_established':False}))


if __name__=='__main__':main()
