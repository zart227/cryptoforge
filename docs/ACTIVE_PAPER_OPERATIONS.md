# Active-universe paper experiment

Started locally on 2026-09-29. Live trading remains stopped. The live pilot
still permits XRP only; the active-universe subclass refuses live mode.

Run on Windows from the repository root:

```powershell
.venv/Scripts/python.exe scripts/run_paper_bot.py
```

Configuration: `config/freqtrade.active-paper.json`. The supervisor removes
inherited Freqtrade environment overrides, forces dry-run and the existing
paper SQLite database, and takes an exclusive process lock. Do not start a
second worker manually. It retries abnormal worker exits up to nine times,
with a 5–60 second backoff. It does not restart after a normal exit and does
not install a Windows startup task. Logs are in `logs/paper-supervisor.*.log`
and `logs/freqtrade-active-paper.log`.

The configuration contains no fixed pair whitelist. Every 30 minutes, take the
top 30 USDT Spot markets by quote volume (minimum
500,000 USDT), filter spreads above 0.3%, sort by volatility over 288 five-minute
candles and keep eight pairs. Exclude stablecoin bases and numbered leveraged
token suffixes. This ranks a liquid shortlist, not every listed market.
The pilot's 5.02 USDT order ceiling, one-position limit, 0.5% stop distance
and daily loss controls remain. Unfilled limit orders time out after five minutes.

The baseline exit now requires a bearish candle at or below resistance for
a resistance rejection. A bullish breakout no longer automatically triggers
both entry and exit. Other exit filters, including overbought RSI, still apply.

Validation: regression tests cover breakout/rejection and paper-only entry
gating. A forced paper worker failure recovered to RUNNING automatically.
A read-only Supabase query succeeded with the new connection timeout and TCP
keepalive parameters. These parameters detect dead connections; they do not
recover interrupted transactions or prove the original network issue resolved.
The paper supervisor does not supervise the live Supabase worker.

`scripts/audit_entry_signals.py` checks closed public candles for supplied pairs.
Its output is a signal diagnostic on whichever universe is current at that
moment, not a permanent pair list, backtest, fill count, profitability result
or daily trade guarantee.
