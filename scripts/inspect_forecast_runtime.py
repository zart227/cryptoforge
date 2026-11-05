#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from cryptoforge.forecast_runtime_inventory import inspect_runtime


def main():
    p=argparse.ArgumentParser(description='Read-only forecast runtime observation')
    p.add_argument('--ledger',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();output=Path(args.output).absolute();ledger=Path(args.ledger).absolute()
    if output.resolve()!=output or not output.parent.is_dir() or output.parent==ledger.parent:
        raise ValueError('separate canonical receipt directory required')
    result=inspect_runtime(ledger)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'output':str(output),'processes_scanned':result['processes_scanned'],
                      'matching_processes':len(result['matching_processes']),'blockers':result['blockers'],
                      'cutover_allowed':False}))


if __name__=='__main__':main()
