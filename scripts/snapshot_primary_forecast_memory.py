"""Create an isolated, read-only-source snapshot of diagnostic forecasts."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cryptoforge.forecast_memory_snapshot import create_forecast_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = create_forecast_snapshot(args.source, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Forecast snapshot blocked: ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
