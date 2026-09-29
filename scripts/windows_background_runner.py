"""Run approved CryptoForge jobs through pythonw without a console window."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_environment(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[name.strip()] = value


def target(target_name: str):  # type: ignore[no-untyped-def]
    if target_name == "executor":
        from scripts.run_supabase_live_executor import main

        return main, ROOT / "logs/supabase-live-executor-task.log"
    if target_name == "collector":
        from scripts.sync_supabase_market_data import main

        return main, ROOT / "logs/research-collector-task.log"
    raise ValueError(f"unsupported background target: {target_name}")


def run() -> int:
    if len(sys.argv) < 2:
        return 2
    target_name = sys.argv[1]
    main, log_path = target(target_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    load_environment(ROOT / ".env")
    sys.argv = [target_name, *sys.argv[2:]]
    with log_path.open("a", encoding="utf-8") as stream:
        with redirect_stdout(stream), redirect_stderr(stream):
            print(f"background_run_started={datetime.now(UTC).isoformat()} target={target_name}", flush=True)
            try:
                result = int(main())
            except Exception:  # preserve diagnostics when no console is attached.
                traceback.print_exc(file=stream)
                return 1
            print(f"background_run_finished={datetime.now(UTC).isoformat()} result={result}", flush=True)
            return result


if __name__ == "__main__":
    raise SystemExit(run())
