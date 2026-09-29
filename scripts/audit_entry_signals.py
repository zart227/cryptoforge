"""Count eligible closed-candle signals, not simulated fills or profits."""
import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

from cryptoforge.market_data import BybitPublicClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'user_data/strategies'))
from CryptoForgeBaselineStrategy import CryptoForgeBaselineStrategy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pairs', nargs='+')
    args = parser.parse_args()
    client = BybitPublicClient(timeout=15)
    strategy = CryptoForgeBaselineStrategy({})
    now = int(time.time() * 1000)
    for pair in args.pairs:
        candles = client.get_klines(pair.replace('/', ''), interval='5', limit=400)
        frame = pd.DataFrame([dict(date=c.start_ms, open=float(c.open),
            high=float(c.high), low=float(c.low), close=float(c.close),
            volume=float(c.volume)) for c in candles if c.close_ms <= now])
        frame = strategy.populate_indicators(frame, {})
        frame = strategy.populate_entry_trend(frame, {})
        frame = strategy.populate_exit_trend(frame, {})
        recent = frame[frame.date >= now - 86_400_000]
        previous_exit = recent.exit_long.eq(1) | recent.near_resistance
        print(json.dumps(dict(pair=pair, candles=len(recent),
            raw_entries=int(recent.enter_long.sum()),
            eligible_before=int((recent.enter_long.eq(1) & ~previous_exit).sum()),
            eligible_after=int((recent.enter_long.eq(1) & recent.exit_long.eq(0)).sum()))), flush=True)


if __name__ == '__main__':
    main()
