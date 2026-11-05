"""Freeze a development protocol or execute one bounded offline experiment."""
import argparse
import os
import sqlite3
from pathlib import Path
from cryptoforge.training_diagnostics import canonical
from cryptoforge.training_experiment_planner import freeze_protocol, read_json, run_experiment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    command = parser.add_subparsers(dest='command', required=True)
    freeze = command.add_parser('freeze')
    freeze.add_argument('--version', required=True)
    freeze.add_argument('--maximum', type=int, default=12)
    freeze.add_argument('--epochs', type=int, default=50)
    run = command.add_parser('run')
    run.add_argument('--protocol', type=Path, required=True)
    run.add_argument('--ledger', type=Path, required=True)
    run.add_argument('--advice-receipt', type=Path)
    args = parser.parse_args(argv)
    # Never train if the output cannot be reserved. Private file, no overwrite.
    try:
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        parser.error('output must be a new writable file')
    receipt = {'status': 'started', 'command': args.command}
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical(receipt)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
        try:
            if args.command == 'freeze':
                result = freeze_protocol(args.dataset, version=args.version, maximum=args.maximum, epochs=args.epochs)
            else:
                proposal = report = None
                if args.advice_receipt:
                    advice = read_json(args.advice_receipt)
                    if advice.get('status') != 'completed':
                        raise ValueError('completed advice receipt required')
                    report = advice['diagnostics']
                    proposal = advice['advice']['proposal']
                protocol = read_json(args.protocol)
                if protocol.get('status') == 'completed' and protocol.get('command') == 'freeze':
                    protocol = protocol['result']
                result = run_experiment(args.dataset, protocol, args.ledger,
                                        proposal=proposal, report=report)
            receipt = {'status': 'completed', 'command': args.command, 'result': result}
            code = 0
        except (ValueError, RuntimeError, OSError, TypeError, KeyError, sqlite3.Error):
            receipt = {'status': 'failed', 'command': args.command,
                       'error': 'offline protocol or experiment rejected; inspect registered evidence'}
            code = 1
        stream.seek(0)
        stream.truncate()
        stream.write(canonical(receipt)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(f"Offline research receipt: {args.output} ({receipt['status']}); no production model changed")
    return code


if __name__ == '__main__':
    raise SystemExit(main())
