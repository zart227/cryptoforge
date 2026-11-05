"""Freeze/inspect research cash contracts and audit application checkpoints.

No .env, market provider, training store, model publication or exchange order I/O.
Actual worker applications use CashWorkerApplication with explicit captured I/O.
"""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.cash_entry_contract import freeze_cash_contract,load_cash_contract,FLAGS
from cryptoforge.cash_worker_application import CashWorkerApplication
from cryptoforge.reference_delivery import ReferenceDelivery
from cryptoforge.local_source_provenance import canonical,parse,read_file


def _json(path):return parse(read_file(path,maximum=131072))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    freeze=sub.add_parser('freeze-contract');freeze.add_argument('--root',required=True,type=Path)
    freeze.add_argument('--queue-reference',required=True,type=Path);freeze.add_argument('--rules',required=True,type=Path)
    freeze.add_argument('--closeout-seconds',required=True,type=int)
    freeze.add_argument('--maximum-decision-latency-seconds',type=int,default=30)
    for name in ('inspect-contract','audit-application'):
        p=sub.add_parser(name);p.add_argument('--reference',required=True,type=Path)
    args=parser.parse_args(argv)
    if args.command=='freeze-contract':
        queue=ReferenceDelivery.open(_json(args.queue_reference))
        result=dict(reference=freeze_cash_contract(args.root,queue,rules=_json(args.rules),closeout_seconds=args.closeout_seconds,
            maximum_decision_latency_seconds=args.maximum_decision_latency_seconds),**FLAGS)
    elif args.command=='inspect-contract':
        value=load_cash_contract(_json(args.reference))
        result={k:value[k] for k in ('schema_version','start','end','entry_cutoff','pairs','rules','strategies','control_scope','price_label_probability_consumed')}
        result.update(FLAGS)
    else:result=CashWorkerApplication.open(_json(args.reference)).audit()
    sys.stdout.buffer.write(canonical(result)+b'\n');return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Cash research command failed: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
