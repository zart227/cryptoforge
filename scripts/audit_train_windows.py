"""Verify original net window study reports against ledger and saved inputs."""
import argparse
import json
import sqlite3
from pathlib import Path
from cryptoforge.train_window_audit import audit_train_window_study


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.report.stat().st_size>16*1024*1024:
            raise ValueError('window report exceeds audit size bound')
        report=json.loads(args.report.read_bytes())
        references=(report['manifest']['original_input_snapshot'],
                    report['manifest']['original_runtime_sources'])
        sizes=[reference['uncompressed_bytes'] for reference in references]
        if any(type(size) is not int or size<=0 for size in sizes) or sum(sizes)>32*1024*1024:
            raise ValueError('original snapshots exceed bounded audit budget')
        result=audit_train_window_study(report,ledger_path=args.ledger)
    except (ValueError,OSError,EOFError,KeyError,TypeError,sqlite3.Error) as exc:
        parser.exit(2,f'window audit unavailable: {exc}\n')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
