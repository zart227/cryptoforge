from __future__ import annotations

import resource
import time

from cryptoforge.market_data import BybitPublicClient
from cryptoforge.scanner import MarketScanner, ScannerConfig


def main() -> int:
    started = time.perf_counter()
    scanner = MarketScanner(
        BybitPublicClient(timeout=15),
        ScannerConfig(
            cheap_shortlist_size=12,
            expensive_shortlist_size=4,
            output_limit=4,
            candle_limit=80,
        ),
    )
    result = scanner.scan()
    elapsed = time.perf_counter() - started
    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    print(f"selected={len(result.selected)}")
    print(f"cheap_candidates={len(result.cheap_candidates)}")
    print(f"rejected={len(result.rejected)}")
    print(f"elapsed_seconds={elapsed:.2f}")
    print(f"max_rss_mb={max_rss_kb / 1024:.1f}")
    for candidate in result.selected:
        print(
            "candidate="
            f"{candidate.symbol} "
            f"score={candidate.score:.4f} "
            f"turnover_24h={candidate.turnover_24h:.0f} "
            f"atr_pct={candidate.atr_pct:.6f} "
            f"momentum_pct={candidate.momentum_pct:.6f} "
            f"oscillation_score={candidate.oscillation_score:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
