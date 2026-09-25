from __future__ import annotations

from cryptoforge.backtesting import baseline_backtest_spec


def main() -> int:
    spec = baseline_backtest_spec()
    freqtrade = "/opt/cryptoforge/app/venv/bin/freqtrade"

    print("# Download bounded historical data")
    print(spec.low_priority_shell_command(spec.download_command(freqtrade)))
    print()
    print("# Run bounded baseline backtest")
    print(spec.low_priority_shell_command(spec.backtest_command(freqtrade)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
