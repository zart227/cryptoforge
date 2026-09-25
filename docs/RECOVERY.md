# Reboot And Crash Recovery

Recovery must prioritize safe trading state over research throughput.

## Startup Order

1. Verify configuration.
2. Verify local state.
3. Start trader.
4. Flush local outbox.
5. Verify monitoring health.
6. Start research only after the trader is healthy and resources are not
   constrained.

Trader starts before research. Heavy research must not auto-start during
constrained recovery.

## Crash Recovery

After a process crash:

1. Confirm dry-run config is still safe.
2. Confirm local state files exist and are readable.
3. Restart the trader only after config and state checks pass.
4. Reopen the local outbox database.
5. Flush due events to Supabase.
6. Check for duplicate trade/event identifiers.
7. Keep research disabled if duplicate trade events are detected.

The local outbox is expected to survive process restart without manual
database repair.

## Controlled Service Restart

A controlled restart should verify:

- service stops cleanly;
- no lingering Freqtrade process remains;
- restart reaches running state;
- dry-run remains enabled;
- Bybit Spot remains configured;
- local outbox remains readable;
- no duplicate trades/events are created.

## Reboot Test Policy

Do not reboot the VPS casually. The current host also runs existing
network/VPN services, so a reboot test requires:

- explicit maintenance window;
- verified status of existing VPS services;
- current backup/migration package;
- rollback plan.

Without those conditions, `RecoveryPlan.allow_reboot_test` remains false.

## Research Recovery

Research is lower priority than trading runtime recovery. It can start
only when:

- trader is already running;
- local state is healthy;
- duplicate trade events are absent;
- resources are not constrained;
- policy explicitly permits research auto-start.

On the current small VPS, heavy research should stay off during recovery.
