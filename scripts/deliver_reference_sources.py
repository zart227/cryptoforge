"""Manage retained reference inputs; never run a trading worker or place orders."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.local_source_provenance import parse,read_file
from cryptoforge.reference_delivery import ReferenceDelivery,ROLES


def descriptor(path):
    value=parse(read_file(path,maximum=65536));return value.get('reference',value)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create');create.add_argument('--output',type=Path,required=True)
    create.add_argument('--source-reference-file',type=Path,required=True);create.add_argument('--diagnostic',action='store_true')
    for name in ('ingest','next','read','ack','audit','recover'):
        command=sub.add_parser(name);command.add_argument('--reference-file',type=Path,required=True)
        if name=='ingest':command.add_argument('--source-reference-file',type=Path,required=True)
        if name in ('next','read','ack'):command.add_argument('--role',choices=ROLES,required=True)
        if name in ('read','ack'):command.add_argument('--delivery-id',required=True)
        if name=='ack':command.add_argument('--worker-receipt-sha256',required=True)
    args=parser.parse_args(argv)
    if args.command=='create':
        result=ReferenceDelivery.create(args.output,descriptor(args.source_reference_file),diagnostic=args.diagnostic).receipt()
    elif args.command=='recover':result=ReferenceDelivery.recover(descriptor(args.reference_file))
    else:
        queue=ReferenceDelivery.open(descriptor(args.reference_file))
        if args.command=='ingest':result=queue.ingest(descriptor(args.source_reference_file))
        elif args.command=='next':result=queue.next(args.role)
        elif args.command=='read':result=queue.read(args.role,args.delivery_id)
        elif args.command=='ack':result=queue.acknowledge(args.role,args.delivery_id,worker_receipt_sha256=args.worker_receipt_sha256)
        else:result=queue.audit()
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Reference delivery failed: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
