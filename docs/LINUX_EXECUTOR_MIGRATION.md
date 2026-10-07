# Linux Spot executor migration

The local executor uses the same guarded arguments as the Windows scheduled
task. Models, research, and decisions are stored in Supabase; holdings and
entry prices are read from Bybit. Local daily equity baseline lives in
`.local/state/live-equity-risk.json`. Preserve that file when moving an
executor during the same UTC day so the daily loss allowance is not reset.

Install a shadow executor (does not submit orders):

```bash
bash deploy/install_local_supabase_executor.sh
```

After a successful shadow cycle, install the live executor:

```bash
bash deploy/install_local_supabase_executor.sh --live
loginctl enable-linger "$USER"
```

Only one trading machine may be active. Before powering the old Windows
laptop back on, prevent its scheduled task from running. With networking
disconnected, run PowerShell as the task owner:

```powershell
Disable-ScheduledTask -TaskName 'CryptoForge Supabase Live Executor'
Stop-ScheduledTask -TaskName 'CryptoForge Supabase Live Executor'
```

Also inspect and disable any independent Freqtrade startup or update task
if present. The local flock prevents duplicate Linux processes on this
machine only; it does not coordinate with the old laptop.

Check operation:

```bash
systemctl --user status cryptoforge-supabase-executor.timer
systemctl --user status cryptoforge-supabase-executor.service
tail -n 80 logs/supabase-live-executor-task.log
loginctl show-user "$USER" -p Linger
```

The timer starts after boot and runs again two minutes after each cycle
finishes. Disable execution with:

```bash
systemctl --user disable --now cryptoforge-supabase-executor.timer
systemctl --user stop cryptoforge-supabase-executor.service
```

This installs the Supabase Spot executor, not the separate Freqtrade runtime.
