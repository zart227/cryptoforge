from __future__ import annotations

import json
import resource
import time
from decimal import Decimal

from cryptoforge.dry_run_pipeline import (
    DryRunPipeline,
    validate_freqtrade_dry_run_config,
)
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.position_management import PositionProtectionPlanner
from cryptoforge.risk import PortfolioState, RiskEngine


def main() -> int:
    config_errors = validate_freqtrade_dry_run_config("config/freqtrade.baseline-dry-run.json")
    if config_errors:
        raise SystemExit(f"unsafe dry-run config: {config_errors}")

    started = time.perf_counter()
    pipeline = DryRunPipeline(
        BybitPublicClient(timeout=15),
        PositionProtectionPlanner(RiskEngine()),
    )
    plans = pipeline.build_plan(
        PortfolioState(
            equity=Decimal("1000"),
            peak_equity=Decimal("1000"),
            daily_realized_pnl=Decimal("0"),
            open_positions=0,
        )
    )
    elapsed = time.perf_counter() - started
    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    print(f"plans={len(plans)}")
    print(f"elapsed_seconds={elapsed:.2f}")
    print(f"max_rss_mb={max_rss_kb / 1024:.1f}")
    print(json.dumps([plan.as_summary() for plan in plans], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
