# Windows GitHub auto-update

`deploy/windows_update.ps1` polls `origin/main` when the current Windows user is logged in. A Task Scheduler job can run it every five minutes. It uses ordinary GitHub read access over the existing `origin` remote; it does not install a GitHub Actions self-hosted runner on the live trading machine.

The updater fails closed. It will not update a dirty or diverged checkout, a dependency-manifest change, or a checkout whose live pilot configuration/risk gates differ from the approved XRP Spot limits. If Freqtrade is trading, it disables new entries and waits for the existing trade and orders to finish while the current bot continues managing exits. Once flat, it backs up the live SQLite database, stops Freqtrade, fast-forwards `main`, validates the strategy and configuration, and restarts the bot. Failed validation leaves the live-entry switch off and records the reason in `data/live-pilot/update-status.json` and `logs/windows-github-update.log`.

The task runs only in the current user's Windows session. Automatic updates therefore pause while that user is signed out or the PC is off. Dependency changes require manual review because this project has no dependency lockfile; the updater does not run `pip install` on code from a push.

Before enabling the scheduled task, the current approved changes in the working tree must be committed and pushed to GitHub. The updater intentionally refuses to overwrite them.
